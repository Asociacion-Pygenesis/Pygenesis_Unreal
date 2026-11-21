#include "PygenesisLightingApplier.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/SkyLightComponent.h"
#include "Editor.h"
#include "Engine/DirectionalLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/SkyLight.h"
#include "Engine/World.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Subsystems/EditorActorSubsystem.h"

DEFINE_LOG_CATEGORY_STATIC(LogPygenesisLighting, Log, All);

namespace PygenesisLighting
{
	double NumField(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Key, double DefaultValue)
	{
		if (!Obj.IsValid())
		{
			return DefaultValue;
		}
		double V = DefaultValue;
		if (Obj->TryGetNumberField(Key, V))
		{
			return V;
		}
		return DefaultValue;
	}

	bool BoolField(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Key, bool DefaultValue)
	{
		if (!Obj.IsValid())
		{
			return DefaultValue;
		}
		bool V = DefaultValue;
		if (Obj->TryGetBoolField(Key, V))
		{
			return V;
		}
		return DefaultValue;
	}

	FVector Vec3Field(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Key, const FVector& DefaultValue)
	{
		if (!Obj.IsValid())
		{
			return DefaultValue;
		}
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (!Obj->TryGetArrayField(Key, Arr) || !Arr || Arr->Num() < 3)
		{
			return DefaultValue;
		}
		return FVector(
			(*Arr)[0]->AsNumber(),
			(*Arr)[1]->AsNumber(),
			(*Arr)[2]->AsNumber());
	}

	template <typename TActor>
	TActor* FindOrSpawn(UEditorActorSubsystem* Subsys, const FVector& Location = FVector::ZeroVector)
	{
		if (!Subsys)
		{
			return nullptr;
		}
		// UE 5.7: no GetAllLevelActorsOfClass — filtrar GetAllLevelActors()
		for (AActor* Actor : Subsys->GetAllLevelActors())
		{
			if (TActor* Typed = Cast<TActor>(Actor))
			{
				return Typed;
			}
		}
		AActor* Spawned = Subsys->SpawnActorFromClass(TActor::StaticClass(), Location, FRotator::ZeroRotator);
		return Cast<TActor>(Spawned);
	}
}

FPygenesisLightingApplyResult FPygenesisLightingApplier::ApplyFromJsonString(const FString& JsonString)
{
	TSharedPtr<FJsonObject> Obj;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonString);
	if (!FJsonSerializer::Deserialize(Reader, Obj) || !Obj.IsValid())
	{
		return {false, TEXT("JSON Lighting-Spec invalido")};
	}
	return ApplyFromJsonObject(Obj);
}

FPygenesisLightingApplyResult FPygenesisLightingApplier::ApplyFromJsonObject(const TSharedPtr<FJsonObject>& Spec)
{
	using namespace PygenesisLighting;

	FPygenesisLightingApplyResult Result;
	if (!Spec.IsValid())
	{
		Result.Message = TEXT("Spec nulo");
		return Result;
	}
	if (!GEditor)
	{
		Result.Message = TEXT("GEditor no disponible");
		return Result;
	}

	UEditorActorSubsystem* Subsys = GEditor->GetEditorSubsystem<UEditorActorSubsystem>();
	if (!Subsys)
	{
		Result.Message = TEXT("EditorActorSubsystem no disponible");
		return Result;
	}

	FString EnvType;
	Spec->TryGetStringField(TEXT("environment_type"), EnvType);
	if (EnvType.IsEmpty())
	{
		EnvType = TEXT("Custom");
	}

	int32 Touched = 0;

	// --- Directional Light ---
	const TSharedPtr<FJsonObject>* DirObj = nullptr;
	if (Spec->TryGetObjectField(TEXT("directional_light"), DirObj) && DirObj && DirObj->IsValid())
	{
		ADirectionalLight* Sun = FindOrSpawn<ADirectionalLight>(Subsys, FVector(0, 0, 400));
		if (Sun)
		{
			if (UDirectionalLightComponent* Comp = Cast<UDirectionalLightComponent>(Sun->GetLightComponent()))
			{
				Comp->SetIntensity(static_cast<float>(NumField(*DirObj, TEXT("intensity"), 10.0)));
				Comp->SetUseTemperature(true);
				Comp->SetTemperature(static_cast<float>(NumField(*DirObj, TEXT("temperature"), 6500.0)));
				Comp->SetCastShadows(BoolField(*DirObj, TEXT("cast_shadows"), true));
			}
			const FVector Rot = Vec3Field(*DirObj, TEXT("rotation"), FVector(-45, 0, 0));
			Sun->SetActorRotation(FRotator(Rot.X, Rot.Y, Rot.Z));
			Sun->SetActorLabel(FString::Printf(TEXT("Pygenesis_Sun_%s"), *EnvType.Left(24)));
			++Touched;
		}
	}

	// --- Sky Light ---
	const TSharedPtr<FJsonObject>* SkyObj = nullptr;
	if (Spec->TryGetObjectField(TEXT("sky_light"), SkyObj) && SkyObj && SkyObj->IsValid())
	{
		ASkyLight* Sky = FindOrSpawn<ASkyLight>(Subsys, FVector(0, 0, 300));
		if (Sky)
		{
			if (USkyLightComponent* Comp = Sky->GetLightComponent())
			{
				Comp->SetIntensity(static_cast<float>(NumField(*SkyObj, TEXT("intensity"), 1.0)));
				Comp->bRealTimeCapture = BoolField(*SkyObj, TEXT("realtime_capture"), true);
				Comp->RecaptureSky();
			}
			Sky->SetActorLabel(TEXT("Pygenesis_SkyLight"));
			++Touched;
		}
	}

	// --- Exponential Height Fog ---
	const TSharedPtr<FJsonObject>* FogObj = nullptr;
	if (Spec->TryGetObjectField(TEXT("exponential_fog"), FogObj) && FogObj && FogObj->IsValid())
	{
		AExponentialHeightFog* Fog = FindOrSpawn<AExponentialHeightFog>(Subsys, FVector(0, 0, 0));
		if (Fog)
		{
			if (UExponentialHeightFogComponent* Comp = Fog->GetComponent())
			{
				Comp->SetFogDensity(static_cast<float>(NumField(*FogObj, TEXT("density"), 0.02)));
				Comp->SetFogHeightFalloff(static_cast<float>(NumField(*FogObj, TEXT("height_falloff"), 0.2)));
				Comp->SetVolumetricFog(BoolField(*FogObj, TEXT("volumetric_fog"), true));
				const FVector Col = Vec3Field(*FogObj, TEXT("inscattering_color"), FVector(0.447, 0.639, 1.0));
				Comp->SetFogInscatteringColor(FLinearColor(Col.X, Col.Y, Col.Z));
			}
			Fog->SetActorLabel(TEXT("Pygenesis_Fog"));
			++Touched;
		}
	}

	// --- Post Process Volume ---
	const TSharedPtr<FJsonObject>* PpObj = nullptr;
	if (Spec->TryGetObjectField(TEXT("post_process"), PpObj) && PpObj && PpObj->IsValid())
	{
		APostProcessVolume* PP = FindOrSpawn<APostProcessVolume>(Subsys, FVector(0, 0, 100));
		if (PP)
		{
			PP->bUnbound = true;
			FPostProcessSettings& S = PP->Settings;
			S.bOverride_AutoExposureBias = true;
			S.AutoExposureBias = static_cast<float>(NumField(*PpObj, TEXT("exposure_compensation"), 0.0));
			S.bOverride_BloomIntensity = true;
			S.BloomIntensity = static_cast<float>(NumField(*PpObj, TEXT("bloom_intensity"), 0.675));
			S.bOverride_VignetteIntensity = true;
			S.VignetteIntensity = static_cast<float>(NumField(*PpObj, TEXT("vignette_intensity"), 0.4));
			PP->SetActorLabel(TEXT("Pygenesis_PostProcess"));
			++Touched;
		}
	}

	if (Touched == 0)
	{
		Result.Message = TEXT("Lighting-Spec sin secciones aplicables");
		return Result;
	}

	Result.bOk = true;
	Result.Message = FString::Printf(
		TEXT("Iluminacion aplicada (%s) | actores tocados=%d (Directional/Sky/Fog/PP)"),
		*EnvType,
		Touched);
	UE_LOG(LogPygenesisLighting, Display, TEXT("%s"), *Result.Message);
	return Result;
}
