#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

struct FPygenesisLightingApplyResult
{
	bool bOk = false;
	FString Message;
};

/**
 * Aplica un Lighting-Spec al nivel abierto:
 * DirectionalLight, SkyLight, ExponentialHeightFog, PostProcessVolume.
 * Crea los actores si faltan.
 */
class FPygenesisLightingApplier
{
public:
	static FPygenesisLightingApplyResult ApplyFromJsonObject(const TSharedPtr<FJsonObject>& Spec);
	static FPygenesisLightingApplyResult ApplyFromJsonString(const FString& JsonString);
};
