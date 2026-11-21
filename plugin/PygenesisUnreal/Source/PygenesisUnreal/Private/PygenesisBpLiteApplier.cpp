#include "PygenesisBpLiteApplier.h"

#include "AssetToolsModule.h"
#include "Components/PrimitiveComponent.h"
#include "EdGraph/EdGraph.h"
#include "EdGraphSchema_K2.h"
#include "Engine/EngineTypes.h"
#include "Factories/BlueprintFactory.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Character.h"
#include "GameFramework/Controller.h"
#include "GameFramework/Pawn.h"
#include "AIController.h"
#include "Blueprint/AIBlueprintHelperLibrary.h"
#include "K2Node_AIMoveTo.h"
#include "K2Node_CallFunction.h"
#include "K2Node_CustomEvent.h"
#include "K2Node_Event.h"
#include "K2Node_IfThenElse.h"
#include "K2Node_InputAction.h"
#include "K2Node_InputKey.h"
#include "K2Node_Knot.h"
#include "K2Node_Self.h"
#include "InputCoreTypes.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetMathLibrary.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/PackageName.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/SavePackage.h"

DEFINE_LOG_CATEGORY_STATIC(LogPygenesisBp, Log, All);

namespace PygenesisBp
{
	struct FNodeSpec
	{
		FString Id;
		FString Type;
		FString Name;
		TSharedPtr<FJsonObject> Inputs;
		TSharedPtr<FJsonObject> Outputs;
		UK2Node* Node = nullptr;
	};

	FString Compact(const FString& S)
	{
		return S.Replace(TEXT(" "), TEXT("")).Replace(TEXT("_"), TEXT("")).ToLower();
	}

	bool BlobHas(const FString& Blob, const TCHAR* Token)
	{
		return Compact(Blob).Contains(Compact(Token));
	}

	bool WantsCharacter(const TArray<TSharedPtr<FJsonValue>>& Nodes)
	{
		for (const TSharedPtr<FJsonValue>& V : Nodes)
		{
			const TSharedPtr<FJsonObject> N = V.IsValid() ? V->AsObject() : nullptr;
			if (!N.IsValid())
			{
				continue;
			}
			FString TypeStr, NameStr;
			N->TryGetStringField(TEXT("type"), TypeStr);
			N->TryGetStringField(TEXT("name"), NameStr);
			const FString Blob = TypeStr + TEXT(" ") + NameStr;
			if (BlobHas(Blob, TEXT("LaunchCharacter")) || BlobHas(Blob, TEXT("CharacterMovement"))
				|| BlobHas(Blob, TEXT("AddMovementInput")) || BlobHas(Blob, TEXT("Jump"))
				|| BlobHas(Blob, TEXT("AIMoveTo")) || BlobHas(Blob, TEXT("SimpleMoveTo")))
			{
				return true;
			}
		}
		return false;
	}

	/** Eventos override nativos de Actor/Pawn/Character (NO CustomEvent). */
	bool ResolveNativeEvent(const FString& Type, const FString& Name, FName& OutEventName, UClass*& OutOwnerClass)
	{
		const FString Blob = Compact(Type + Name);
		OutOwnerClass = AActor::StaticClass();

		if (Blob.Contains(TEXT("beginplay")) || Blob.Contains(TEXT("eventbeginplay")) || Blob.Contains(TEXT("receivebeginplay")))
		{
			OutEventName = FName(TEXT("ReceiveBeginPlay"));
			return true;
		}
		if (Blob.Contains(TEXT("eventtick")) || Blob.Contains(TEXT("receivetick")) || Blob == TEXT("tick"))
		{
			OutEventName = FName(TEXT("ReceiveTick"));
			return true;
		}
		if (Blob.Contains(TEXT("actorbeginoverlap")) || Blob.Contains(TEXT("beginoverlap")) || Blob.Contains(TEXT("onactorbeginoverlap")))
		{
			OutEventName = FName(TEXT("ReceiveActorBeginOverlap"));
			return true;
		}
		if (Blob.Contains(TEXT("actorendoverlap")) || Blob.Contains(TEXT("endoverlap")))
		{
			OutEventName = FName(TEXT("ReceiveActorEndOverlap"));
			return true;
		}
		if (Blob.Contains(TEXT("actorhit")) || Blob.Contains(TEXT("onactorhit")) || Blob == TEXT("eventhit"))
		{
			OutEventName = FName(TEXT("ReceiveHit"));
			return true;
		}
		if (Blob.Contains(TEXT("destroyed")) || Blob.Contains(TEXT("ondestroyed")))
		{
			OutEventName = FName(TEXT("ReceiveDestroyed"));
			return true;
		}
		if (Blob.Contains(TEXT("endplay")) || Blob.Contains(TEXT("receiveendplay")))
		{
			OutEventName = FName(TEXT("ReceiveEndPlay"));
			return true;
		}
		if (Blob.Contains(TEXT("possessed")))
		{
			OutEventName = FName(TEXT("ReceivePossessed"));
			OutOwnerClass = APawn::StaticClass();
			return true;
		}
		if (Blob.Contains(TEXT("unpossessed")))
		{
			OutEventName = FName(TEXT("ReceiveUnpossessed"));
			OutOwnerClass = APawn::StaticClass();
			return true;
		}
		return false;
	}

	bool IsInputKey(const FString& Type, const FString& Name)
	{
		const FString Blob = Compact(Type + Name);
		// InputKey canónico + dialecto Ollama Event_InputAction_F / InputAction_W
		if (Blob.Contains(TEXT("inputkey")) || Blob.Contains(TEXT("spacebar"))
			|| Blob == TEXT("space") || Blob.Contains(TEXT("tecla")))
		{
			return true;
		}
		if (Blob.Contains(TEXT("inputaction")))
		{
			// Tecla física (F/W/A/D/Space) → InputKey; no Enhanced Input asset
			return true;
		}
		return false;
	}

	bool IsInputAction(const FString& Type, const FString& Name)
	{
		const FString Blob = Compact(Type + Name);
		// Tras preferir InputKey para InputAction_*, solo queda IA_ genérica / jump mapping
		if (Blob.Contains(TEXT("inputaction")) || Blob.Contains(TEXT("ia_")))
		{
			return false; // manejado como InputKey arriba
		}
		return Blob.Contains(TEXT("input")) && (Blob.Contains(TEXT("pressed")) || Blob.Contains(TEXT("jump")) || Blob.Contains(TEXT("action")));
	}

	FKey ExtractInputKey(const FString& Name)
	{
		const FString Blob = Compact(Name);
		if (Blob.Contains(TEXT("space")) || Blob.Contains(TEXT("jump")))
		{
			return EKeys::SpaceBar;
		}
		// Event_InputAction_F / InputAction_W → letra final
		{
			const int32 Idx = Blob.Find(TEXT("inputaction"));
			if (Idx != INDEX_NONE)
			{
				FString Tail = Blob.Mid(Idx + 11); // len("inputaction")
				Tail.ReplaceInline(TEXT("_"), TEXT(""));
				if (Tail.Contains(TEXT("space")) || Tail.Contains(TEXT("jump")))
				{
					return EKeys::SpaceBar;
				}
				if (Tail.Len() >= 1 && FChar::IsAlpha(Tail[0]))
				{
					const FString Letter = Tail.Left(1).ToUpper();
					return FKey(*Letter);
				}
			}
		}
		// Tecla suelta: "F", "E", "InputKey F", "Pressed F"...
		if (Blob.Len() == 1 && FChar::IsAlpha(Blob[0]))
		{
			return FKey(*Blob.ToUpper());
		}
		for (TCHAR C = TEXT('A'); C <= TEXT('Z'); ++C)
		{
			const FString Letter(1, &C);
			if (Blob == Letter || Blob.EndsWith(Letter) || Blob.Contains(TEXT("key") + Letter)
				|| Blob.Contains(Letter + TEXT("key")) || Blob.Contains(TEXT("tecla") + Letter))
			{
				return FKey(*Letter);
			}
		}
		if (!Blob.IsEmpty())
		{
			const FKey Key(*Name.TrimStartAndEnd());
			if (Key.IsValid())
			{
				return Key;
			}
			const FKey KeyBlob(*Blob);
			if (KeyBlob.IsValid())
			{
				return KeyBlob;
			}
		}
		return EKeys::SpaceBar;
	}

	FName ExtractInputActionName(const FString& Name)
	{
		FString Clean = Name;
		Clean.ReplaceInline(TEXT("InputAction"), TEXT(""));
		Clean.ReplaceInline(TEXT("Input Action"), TEXT(""));
		Clean.ReplaceInline(TEXT("IA_"), TEXT(""));
		Clean.TrimStartAndEndInline();
		if (Clean.IsEmpty())
		{
			Clean = TEXT("Jump");
		}
		return FName(*Clean);
	}

	UFunction* ResolveFunction(const FString& Name, UClass* PreferredClass)
	{
		const FString CompactName = Name.Replace(TEXT(" "), TEXT(""));

		auto FindInClass = [](UClass* Cls, FName FuncName) -> UFunction*
		{
			return Cls ? Cls->FindFunctionByName(FuncName) : nullptr;
		};

		if (CompactName.Equals(TEXT("LaunchCharacter"), ESearchCase::IgnoreCase)
			|| CompactName.StartsWith(TEXT("LaunchCharacter"), ESearchCase::IgnoreCase))
		{
			return FindInClass(ACharacter::StaticClass(), GET_FUNCTION_NAME_CHECKED(ACharacter, LaunchCharacter));
		}
		if (CompactName.Equals(TEXT("Jump"), ESearchCase::IgnoreCase))
		{
			return FindInClass(ACharacter::StaticClass(), GET_FUNCTION_NAME_CHECKED(ACharacter, Jump));
		}
		if (CompactName.Equals(TEXT("StopJumping"), ESearchCase::IgnoreCase))
		{
			return FindInClass(ACharacter::StaticClass(), GET_FUNCTION_NAME_CHECKED(ACharacter, StopJumping));
		}
		if (CompactName.Equals(TEXT("AddMovementInput"), ESearchCase::IgnoreCase)
			|| CompactName.StartsWith(TEXT("AddMovementInput"), ESearchCase::IgnoreCase))
		{
			// "Add Movement Input Forward/Left/Right" (dialecto Ollama)
			return FindInClass(APawn::StaticClass(), GET_FUNCTION_NAME_CHECKED(APawn, AddMovementInput));
		}
		if (CompactName.Contains(TEXT("GetActorLocation")))
		{
			return FindInClass(AActor::StaticClass(), GET_FUNCTION_NAME_CHECKED(AActor, K2_GetActorLocation));
		}
		if (CompactName.Contains(TEXT("SetActorLocation")))
		{
			return FindInClass(AActor::StaticClass(), GET_FUNCTION_NAME_CHECKED(AActor, K2_SetActorLocation));
		}
		if (CompactName.Contains(TEXT("DestroyActor")))
		{
			return FindInClass(AActor::StaticClass(), GET_FUNCTION_NAME_CHECKED(AActor, K2_DestroyActor));
		}
		if (CompactName.Contains(TEXT("LineTrace")))
		{
			return FindInClass(UKismetSystemLibrary::StaticClass(), GET_FUNCTION_NAME_CHECKED(UKismetSystemLibrary, LineTraceSingle));
		}
		if (CompactName.Contains(TEXT("PrintString")) || CompactName.Equals(TEXT("Print"), ESearchCase::IgnoreCase))
		{
			return FindInClass(UKismetSystemLibrary::StaticClass(), GET_FUNCTION_NAME_CHECKED(UKismetSystemLibrary, PrintString));
		}
		if (CompactName.Equals(TEXT("Delay"), ESearchCase::IgnoreCase))
		{
			return FindInClass(UKismetSystemLibrary::StaticClass(), FName(TEXT("Delay")));
		}
		if (CompactName.Contains(TEXT("GetPlayerCharacter")))
		{
			return FindInClass(UGameplayStatics::StaticClass(), GET_FUNCTION_NAME_CHECKED(UGameplayStatics, GetPlayerCharacter));
		}
		if (CompactName.Contains(TEXT("GetPlayerController")))
		{
			return FindInClass(UGameplayStatics::StaticClass(), GET_FUNCTION_NAME_CHECKED(UGameplayStatics, GetPlayerController));
		}
		if (CompactName.Contains(TEXT("AIMoveToActor"))
			|| CompactName.Equals(TEXT("SimpleMoveToActor"), ESearchCase::IgnoreCase))
		{
			return FindInClass(
				UAIBlueprintHelperLibrary::StaticClass(),
				GET_FUNCTION_NAME_CHECKED(UAIBlueprintHelperLibrary, SimpleMoveToActor));
		}
		// Simple Move to Location: Goal es const FVector& y no admite un literal.
		// AIMoveTo (el nodo del menú) se crea aparte, como UK2Node_AIMoveTo.
		if (CompactName.Equals(TEXT("SimpleMoveToLocation"), ESearchCase::IgnoreCase))
		{
			return FindInClass(
				UAIBlueprintHelperLibrary::StaticClass(),
				GET_FUNCTION_NAME_CHECKED(UAIBlueprintHelperLibrary, SimpleMoveToLocation));
		}

		TArray<FString> Variants;
		Variants.Add(CompactName);
		Variants.Add(FString(TEXT("K2_")) + CompactName);
		if (CompactName.StartsWith(TEXT("K2_")))
		{
			Variants.Add(CompactName.RightChop(3));
		}

		UClass* Classes[] = {
			PreferredClass,
			AActor::StaticClass(),
			APawn::StaticClass(),
			ACharacter::StaticClass(),
			AController::StaticClass(),
			AAIController::StaticClass(),
			UKismetSystemLibrary::StaticClass(),
			UGameplayStatics::StaticClass(),
			UKismetMathLibrary::StaticClass(),
			UAIBlueprintHelperLibrary::StaticClass(),
		};
		for (UClass* Cls : Classes)
		{
			if (!Cls)
			{
				continue;
			}
			for (const FString& Variant : Variants)
			{
				if (UFunction* Found = Cls->FindFunctionByName(FName(*Variant)))
				{
					return Found;
				}
			}
		}
		UE_LOG(LogTemp, Warning, TEXT("Pygenesis BP-Lite: función no resuelta '%s' (omitida)"), *Name);
		return nullptr;
	}

	UEdGraphPin* FindExecOut(UK2Node* Node, const FString& PreferredName = FString())
	{
		if (!Node)
		{
			return nullptr;
		}
		if (!PreferredName.IsEmpty())
		{
			if (UEdGraphPin* P = Node->FindPin(*PreferredName, EGPD_Output))
			{
				if (P->PinType.PinCategory == UEdGraphSchema_K2::PC_Exec)
				{
					return P;
				}
			}
			// Branch: el modelo nombra las ramas de muchas formas (then, True, TrueNodeID…)
			const FString Wanted = Compact(PreferredName);
			if (Wanted.Contains(TEXT("false")) || Wanted.Contains(TEXT("else")))
			{
				if (UEdGraphPin* P = Node->FindPin(UEdGraphSchema_K2::PN_Else))
				{
					return P;
				}
			}
			if (Wanted.Contains(TEXT("true")) || Wanted.Contains(TEXT("then")))
			{
				if (UEdGraphPin* P = Node->FindPin(UEdGraphSchema_K2::PN_Then))
				{
					return P;
				}
			}
			if (PreferredName.Contains(TEXT("Pressed")))
			{
				if (UEdGraphPin* P = Node->FindPin(TEXT("Pressed")))
				{
					return P;
				}
			}
		}
		if (UEdGraphPin* ThenPin = Node->FindPin(UEdGraphSchema_K2::PN_Then))
		{
			return ThenPin;
		}
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (Pin && Pin->Direction == EGPD_Output && Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_Exec)
			{
				return Pin;
			}
		}
		return nullptr;
	}

	UEdGraphPin* FindExecIn(UK2Node* Node)
	{
		if (!Node)
		{
			return nullptr;
		}
		if (UEdGraphPin* Exec = Node->FindPin(UEdGraphSchema_K2::PN_Execute))
		{
			return Exec;
		}
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (Pin && Pin->Direction == EGPD_Input && Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_Exec)
			{
				return Pin;
			}
		}
		return nullptr;
	}

	void TryWireExec(UK2Node* From, UK2Node* To, const FString& FromPinName = FString())
	{
		UEdGraphPin* OutPin = FindExecOut(From, FromPinName);
		UEdGraphPin* InPin = FindExecIn(To);
		if (OutPin && InPin && !OutPin->LinkedTo.Contains(InPin))
		{
			OutPin->MakeLinkTo(InPin);
		}
	}

	/**
	 * Los nombres de pin que emite el middleware no siempre coinciden con los de UE
	 * (WorldDirectionVector vs WorldDirection, XYOverride vs bXYOverride). Sin alias,
	 * FindPin falla en silencio y el pin se queda con su valor por defecto.
	 */
	UEdGraphPin* FindPinWithAliases(UK2Node* Node, const FString& Key)
	{
		if (!Node)
		{
			return nullptr;
		}
		if (UEdGraphPin* P = Node->FindPin(*Key))
		{
			return P;
		}

		static const TMap<FString, TArray<FString>> Aliases = {
			{TEXT("worlddirectionvector"), {TEXT("WorldDirection")}},
			{TEXT("direction"), {TEXT("WorldDirection")}},
			{TEXT("worlddirection"), {TEXT("WorldDirectionVector")}},
			{TEXT("xyoverride"), {TEXT("bXYOverride")}},
			{TEXT("zoverride"), {TEXT("bZOverride")}},
			{TEXT("force"), {TEXT("bForce")}},
			{TEXT("instring"), {TEXT("InString"), TEXT("String")}},
			{TEXT("duration"), {TEXT("Duration"), TEXT("Time")}},
			{TEXT("condition"), {TEXT("Condition")}},
			{TEXT("destination"), {TEXT("Goal"), TEXT("Destination")}},
			{TEXT("goal"), {TEXT("Destination"), TEXT("Goal")}},
		};

		const TArray<FString>* Candidates = Aliases.Find(Compact(Key));
		if (Candidates)
		{
			for (const FString& Candidate : *Candidates)
			{
				if (UEdGraphPin* P = Node->FindPin(*Candidate))
				{
					return P;
				}
			}
		}
		// Último recurso: el mismo nombre salvo el prefijo booleano o un sufijo
		// "Vector"/"Value" de adorno. Nada más laxo: emparejar por substring
		// acabaría escribiendo en el pin equivocado.
		const FString Wanted = Compact(Key);
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (!Pin || Pin->Direction != EGPD_Input)
			{
				continue;
			}
			FString PinName = Compact(Pin->PinName.ToString());
			if (PinName.StartsWith(TEXT("b")))
			{
				PinName = PinName.RightChop(1);
			}
			if (PinName == Wanted
				|| PinName + TEXT("vector") == Wanted
				|| PinName == Wanted + TEXT("vector")
				|| PinName + TEXT("value") == Wanted
				|| PinName == Wanted + TEXT("value"))
			{
				return Pin;
			}
		}
		return nullptr;
	}

	bool IsRotatorStructPin(const UEdGraphPin* Pin)
	{
		if (!Pin || Pin->PinType.PinCategory != UEdGraphSchema_K2::PC_Struct)
		{
			return false;
		}
		const UObject* Sub = Pin->PinType.PinSubCategoryObject.Get();
		return Sub && Sub->GetFName() == TEXT("Rotator");
	}

	bool IsVectorStructPin(const UEdGraphPin* Pin)
	{
		if (!Pin || Pin->PinType.PinCategory != UEdGraphSchema_K2::PC_Struct)
		{
			return false;
		}
		const UObject* Sub = Pin->PinType.PinSubCategoryObject.Get();
		return Sub && Sub->GetFName() == TEXT("Vector");
	}

	bool TryParseVectorString(FString S, FVector& Out)
	{
		S.ReplaceInline(TEXT("["), TEXT(""));
		S.ReplaceInline(TEXT("]"), TEXT(""));
		S.ReplaceInline(TEXT("("), TEXT(""));
		S.ReplaceInline(TEXT(")"), TEXT(""));
		S.ReplaceInline(TEXT(" "), TEXT(""));
		TArray<FString> Parts;
		S.ParseIntoArray(Parts, TEXT(","), true);
		if (Parts.Num() < 3)
		{
			return false;
		}
		Out = FVector(FCString::Atod(*Parts[0]), FCString::Atod(*Parts[1]), FCString::Atod(*Parts[2]));
		return true;
	}

	// NewObject deja NodeGuid a cero. Dos AI MoveTo latentes generan entonces
	// la misma función (OnSuccess_<guid>) y el compilador dice que hay dos
	// funciones con el mismo nombre.
	void StampNewNode(UEdGraphNode* Node)
	{
		if (Node)
		{
			Node->CreateNewGuid();
		}
	}

	/**
	 * Un pin const FVector& (Goal de SimpleMoveToLocation) no acepta default:
	 * Unreal exige un cable. En ese caso se crea Make Vector y se conecta.
	 * Un FVector por valor (Destination de AI MoveTo) sí admite el literal.
	 */
	void SetVectorPin(UK2Node* Node, UEdGraphPin* Pin, const FVector& Value)
	{
		if (!Node || !Pin)
		{
			return;
		}
		if (Pin->PinType.bIsReference)
		{
			UEdGraph* Graph = Node->GetGraph();
			UFunction* MakeFn = UKismetMathLibrary::StaticClass()->FindFunctionByName(
				GET_FUNCTION_NAME_CHECKED(UKismetMathLibrary, MakeVector));
			if (!Graph || !MakeFn)
			{
				return;
			}
			UK2Node_CallFunction* Make = NewObject<UK2Node_CallFunction>(Graph);
			StampNewNode(Make);
			Make->SetFromFunction(MakeFn);
			Make->AllocateDefaultPins();
			Make->NodePosX = Node->NodePosX - 240;
			Make->NodePosY = Node->NodePosY + 140;
			Graph->AddNode(Make, false, false);
			auto SetAxis = [&](const TCHAR* Axis, double AxisValue)
			{
				if (UEdGraphPin* AxisPin = Make->FindPin(Axis))
				{
					AxisPin->DefaultValue = FString::SanitizeFloat(AxisValue);
				}
			};
			SetAxis(TEXT("X"), Value.X);
			SetAxis(TEXT("Y"), Value.Y);
			SetAxis(TEXT("Z"), Value.Z);
			if (UEdGraphPin* Ret = Make->FindPin(UEdGraphSchema_K2::PN_ReturnValue))
			{
				Ret->MakeLinkTo(Pin);
			}
			return;
		}
		Pin->DefaultValue = FString::Printf(TEXT("%g,%g,%g"), Value.X, Value.Y, Value.Z);
	}

	void WireSelfToPin(UEdGraph* EventGraph, UK2Node* Node, const TCHAR* PinName, int32 X, int32 Y)
	{
		if (!EventGraph || !Node)
		{
			return;
		}
		UEdGraphPin* Target = Node->FindPin(PinName, EGPD_Input);
		if (!Target || Target->LinkedTo.Num() > 0)
		{
			return;
		}
		UK2Node_Self* SelfNode = NewObject<UK2Node_Self>(EventGraph);
		StampNewNode(SelfNode);
		SelfNode->AllocateDefaultPins();
		SelfNode->NodePosX = X;
		SelfNode->NodePosY = Y;
		EventGraph->AddNode(SelfNode, false, false);
		if (UEdGraphPin* SelfOut = SelfNode->FindPin(UEdGraphSchema_K2::PN_Self, EGPD_Output))
		{
			SelfOut->MakeLinkTo(Target);
		}
	}

	void ApplyDefaultsFromInputs(UK2Node* Node, const TSharedPtr<FJsonObject>& Inputs, const FString& FuncName)
	{
		if (!Node || !Inputs.IsValid())
		{
			return;
		}

		auto SetPinNumber = [&](const TCHAR* PinName, double Value)
		{
			if (UEdGraphPin* P = FindPinWithAliases(Node, PinName))
			{
				P->DefaultValue = FString::SanitizeFloat(Value);
			}
		};

		auto SetPinBool = [&](const TCHAR* PinName, bool bValue)
		{
			if (UEdGraphPin* P = FindPinWithAliases(Node, PinName))
			{
				P->DefaultValue = bValue ? TEXT("true") : TEXT("false");
			}
		};

		auto SetPinString = [&](const TCHAR* PinName, const FString& Value)
		{
			if (UEdGraphPin* P = FindPinWithAliases(Node, PinName))
			{
				P->DefaultValue = Value;
			}
		};

		// LaunchCharacter: LaunchVelocity / XYOverride / ZOverride
		if (FuncName.Contains(TEXT("LaunchCharacter")))
		{
			const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
			if (Inputs->TryGetArrayField(TEXT("LaunchVelocity"), Arr) && Arr && Arr->Num() >= 3)
			{
				const double X = (*Arr)[0]->AsNumber();
				const double Y = (*Arr)[1]->AsNumber();
				const double Z = (*Arr)[2]->AsNumber();
				if (UEdGraphPin* P = FindPinWithAliases(Node, TEXT("LaunchVelocity")))
				{
					P->DefaultValue = FString::Printf(TEXT("%g,%g,%g"), X, Y, Z);
				}
			}
			else if (Inputs->HasField(TEXT("LaunchVelocity")))
			{
				// "(0, 0, 700)" string
				FString S;
				if (Inputs->TryGetStringField(TEXT("LaunchVelocity"), S))
				{
					if (UEdGraphPin* P = Node->FindPin(TEXT("LaunchVelocity")))
					{
						S.ReplaceInline(TEXT("("), TEXT(""));
						S.ReplaceInline(TEXT(")"), TEXT(""));
						S.ReplaceInline(TEXT(" "), TEXT(""));
						P->DefaultValue = S;
					}
				}
			}
			else
			{
				// Default util para jump
				if (UEdGraphPin* P = Node->FindPin(TEXT("LaunchVelocity")))
				{
					P->DefaultValue = TEXT("0.0,0.0,700.0");
				}
			}
			bool bXY = true, bZ = true;
			Inputs->TryGetBoolField(TEXT("XYOverride"), bXY);
			Inputs->TryGetBoolField(TEXT("ZOverride"), bZ);
			SetPinBool(TEXT("bXYOverride"), bXY);
			SetPinBool(TEXT("bZOverride"), bZ);
			// Algunas firmas usan XYOverride sin b
			SetPinBool(TEXT("XYOverride"), bXY);
			SetPinBool(TEXT("ZOverride"), bZ);
		}

		if (FuncName.Contains(TEXT("PrintString")))
		{
			FString Msg;
			if (!Inputs->TryGetStringField(TEXT("InString"), Msg))
			{
				Inputs->TryGetStringField(TEXT("value"), Msg);
			}
			if (!Msg.IsEmpty())
			{
				SetPinString(TEXT("InString"), Msg);
			}
		}

		if (FuncName.Contains(TEXT("Delay")))
		{
			double Dur = 1.0;
			if (Inputs->TryGetNumberField(TEXT("Duration"), Dur) || Inputs->TryGetNumberField(TEXT("duration"), Dur))
			{
				SetPinNumber(TEXT("Duration"), Dur);
			}
		}

		// Generico: copiar strings/numbers/bools a pines del mismo nombre
		for (const auto& Pair : Inputs->Values)
		{
			const FString& Key = Pair.Key;
			if (Key.StartsWith(TEXT("exec")) || Key.Contains(TEXT(".")))
			{
				continue;
			}
			UEdGraphPin* Pin = FindPinWithAliases(Node, Key);
			if (!Pin || Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_Exec)
			{
				UE_CLOG(!Pin, LogPygenesisBp, Warning,
					TEXT("Pygenesis BP-Lite: pin '%s' no existe en %s (valor ignorado)"),
					*Key, *FuncName);
				continue;
			}
			const TSharedPtr<FJsonValue> V = Pair.Value;
			if (!V.IsValid())
			{
				continue;
			}
			if (V->Type == EJson::Number)
			{
				Pin->DefaultValue = FString::SanitizeFloat(V->AsNumber());
			}
			else if (V->Type == EJson::Boolean)
			{
				Pin->DefaultValue = V->AsBool() ? TEXT("true") : TEXT("false");
			}
			else if (V->Type == EJson::String)
			{
				FString S = V->AsString();
				// Ignorar refs a otros nodos
				if (S.Contains(TEXT("node_")) || S.Contains(TEXT(".exec")))
				{
					continue;
				}
				FVector Parsed;
				if (IsVectorStructPin(Pin) && TryParseVectorString(S, Parsed))
				{
					SetVectorPin(Node, Pin, Parsed);
				}
				else if (IsRotatorStructPin(Pin) && TryParseVectorString(S, Parsed))
				{
					// FRotator guarda Pitch,Yaw,Roll. En el pin, Z es el yaw.
					Pin->DefaultValue = FString::Printf(TEXT("%g,%g,%g"), Parsed.X, Parsed.Y, Parsed.Z);
				}
				else
				{
					Pin->DefaultValue = S;
				}
			}
			else if (V->Type == EJson::Array)
			{
				const TArray<TSharedPtr<FJsonValue>> Arr = V->AsArray();
				if (Arr.Num() == 3 && Arr[0].IsValid() && Arr[0]->Type == EJson::Number)
				{
					const FVector Parsed(Arr[0]->AsNumber(), Arr[1]->AsNumber(), Arr[2]->AsNumber());
					if (IsVectorStructPin(Pin))
					{
						SetVectorPin(Node, Pin, Parsed);
					}
					else
					{
						Pin->DefaultValue = FString::Printf(
							TEXT("%g,%g,%g"),
							Parsed.X, Parsed.Y, Parsed.Z);
					}
				}
			}
		}
	}

	UK2Node* SpawnNativeEvent(UEdGraph* EventGraph, UClass* ParentClass, FName EventName, UClass* OwnerClass, int32 X, int32 Y)
	{
		UK2Node_Event* Ev = NewObject<UK2Node_Event>(EventGraph);
		StampNewNode(Ev);
		UClass* UseClass = OwnerClass ? OwnerClass : ParentClass;
		// Preferir la clase padre del BP si implementa el evento
		if (ParentClass && ParentClass->FindFunctionByName(EventName))
		{
			UseClass = ParentClass;
		}
		Ev->EventReference.SetExternalMember(EventName, UseClass);
		Ev->bOverrideFunction = true;
		Ev->AllocateDefaultPins();
		Ev->NodePosX = X;
		Ev->NodePosY = Y;
		EventGraph->AddNode(Ev, false, false);
		return Ev;
	}

	UK2Node* SpawnInputAction(UEdGraph* EventGraph, FName ActionName, int32 X, int32 Y)
	{
		UK2Node_InputAction* Input = NewObject<UK2Node_InputAction>(EventGraph);
		StampNewNode(Input);
		Input->InputActionName = ActionName;
		Input->AllocateDefaultPins();
		Input->NodePosX = X;
		Input->NodePosY = Y;
		EventGraph->AddNode(Input, false, false);
		return Input;
	}

	UK2Node* SpawnInputKey(UEdGraph* EventGraph, FKey Key, int32 X, int32 Y)
	{
		UK2Node_InputKey* Input = NewObject<UK2Node_InputKey>(EventGraph);
		StampNewNode(Input);
		Input->InputKey = Key;
		Input->AllocateDefaultPins();
		Input->NodePosX = X;
		Input->NodePosY = Y;
		EventGraph->AddNode(Input, false, false);
		return Input;
	}

	void ClearAutoGeneratedDefaultEvents(UEdGraph* EventGraph)
	{
		// UE inserta stubs BeginPlay/Tick/Overlap vía [DefaultEventNodes] al crear Actor BPs.
		if (!EventGraph)
		{
			return;
		}
		TArray<UEdGraphNode*> ToRemove;
		for (UEdGraphNode* Node : EventGraph->Nodes)
		{
			UK2Node_Event* Ev = Cast<UK2Node_Event>(Node);
			if (!Ev)
			{
				continue;
			}
			const FString EvName = Ev->GetFunctionName().ToString();
			if (EvName.Equals(TEXT("ReceiveBeginPlay"))
				|| EvName.Equals(TEXT("ReceiveTick"))
				|| EvName.Equals(TEXT("ReceiveActorBeginOverlap"))
				|| EvName.Equals(TEXT("ReceiveActorEndOverlap")))
			{
				// Solo si no tienen cables (stubs de plantilla)
				bool bLinked = false;
				for (UEdGraphPin* Pin : Ev->Pins)
				{
					if (Pin && Pin->LinkedTo.Num() > 0)
					{
						bLinked = true;
						break;
					}
				}
				if (!bLinked)
				{
					ToRemove.Add(Node);
				}
			}
		}
		for (UEdGraphNode* Node : ToRemove)
		{
			EventGraph->RemoveNode(Node);
		}
	}

	UK2Node* SpawnCustomEvent(UEdGraph* EventGraph, const FString& Name, int32 X, int32 Y)
	{
		UK2Node_CustomEvent* Ev = NewObject<UK2Node_CustomEvent>(EventGraph);
		StampNewNode(Ev);
		Ev->CustomFunctionName = FName(*Name.Replace(TEXT(" "), TEXT("_")));
		Ev->AllocateDefaultPins();
		Ev->NodePosX = X;
		Ev->NodePosY = Y;
		EventGraph->AddNode(Ev, false, false);
		return Ev;
	}

	void ParseRef(const FString& Ref, FString& OutNodeId, FString& OutPin)
	{
		OutNodeId.Reset();
		OutPin.Reset();
		FString Trimmed = Ref.TrimStartAndEnd();
		int32 Dot = INDEX_NONE;
		if (Trimmed.FindChar(TEXT('.'), Dot))
		{
			OutNodeId = Trimmed.Left(Dot);
			OutPin = Trimmed.Mid(Dot + 1);
		}
		else
		{
			OutNodeId = Trimmed;
			OutPin = TEXT("exec_in");
		}
		// Normalizar id numerico
		if (OutNodeId.IsNumeric())
		{
			OutNodeId = FString::Printf(TEXT("node_%02d"), FCString::Atoi(*OutNodeId));
		}
	}

	bool IsExecPinName(const FString& Name)
	{
		const FString C = Compact(Name);
		return C == TEXT("execin") || C == TEXT("execout") || C == TEXT("execute")
			|| C == TEXT("then") || C == TEXT("else") || C == TEXT("pressed") || C == TEXT("released");
	}

	bool DataPinAlreadyReaches(const UEdGraphPin* OutPin, const UEdGraphPin* InPin)
	{
		if (!OutPin || !InPin)
		{
			return false;
		}
		if (OutPin->LinkedTo.Contains(InPin))
		{
			return true;
		}
		// TryCreateConnection mete un conversor en medio (p.ej. GetDisplayName).
		// El pin de salida no apunta al destino, así que un segundo cable
		// crearía otro conversor igual.
		for (const UEdGraphPin* Hop : OutPin->LinkedTo)
		{
			const UEdGraphNode* Mid = Hop ? Hop->GetOwningNode() : nullptr;
			if (!Mid)
			{
				continue;
			}
			for (const UEdGraphPin* MidPin : Mid->Pins)
			{
				if (MidPin && MidPin->Direction == EGPD_Output && MidPin->LinkedTo.Contains(InPin))
				{
					return true;
				}
			}
		}
		return false;
	}

	void TryWireData(UK2Node* From, const FString& FromPinName, UK2Node* To, const FString& ToPinName)
	{
		if (!From || !To || FromPinName.IsEmpty() || ToPinName.IsEmpty())
		{
			return;
		}
		UEdGraphPin* OutPin = From->FindPin(*FromPinName, EGPD_Output);
		UEdGraphPin* InPin = To->FindPin(*ToPinName, EGPD_Input);
		if (!InPin)
		{
			InPin = FindPinWithAliases(To, ToPinName);
			if (InPin && InPin->Direction != EGPD_Input)
			{
				InPin = nullptr;
			}
		}
		if (!OutPin || !InPin
			|| OutPin->PinType.PinCategory == UEdGraphSchema_K2::PC_Exec
			|| InPin->PinType.PinCategory == UEdGraphSchema_K2::PC_Exec
			|| DataPinAlreadyReaches(OutPin, InPin))
		{
			return;
		}
		if (const UEdGraphSchema* Schema = OutPin->GetSchema())
		{
			Schema->TryCreateConnection(OutPin, InPin);
		}
	}

	void WireFromOutputs(const TArray<FNodeSpec>& Specs, const TMap<FString, UK2Node*>& Map)
	{
		for (const FNodeSpec& Spec : Specs)
		{
			if (!Spec.Node || !Spec.Outputs.IsValid())
			{
				continue;
			}
			for (const auto& Pair : Spec.Outputs->Values)
			{
				const FString FromPin = Pair.Key;
				const TSharedPtr<FJsonValue> Val = Pair.Value;
				if (!Val.IsValid() || Val->IsNull())
				{
					continue;
				}

				TArray<FString> Targets;
				if (Val->Type == EJson::String)
				{
					Targets.Add(Val->AsString());
				}
				else if (Val->Type == EJson::Array)
				{
					for (const TSharedPtr<FJsonValue>& Item : Val->AsArray())
					{
						if (Item.IsValid() && Item->Type == EJson::String)
						{
							Targets.Add(Item->AsString());
						}
					}
				}

				for (const FString& TargetRef : Targets)
				{
					FString TargetId, TargetPin;
					ParseRef(TargetRef, TargetId, TargetPin);
					UK2Node* const* TargetPtr = Map.Find(TargetId);
					if (!TargetPtr || !*TargetPtr)
					{
						continue;
					}
					if (IsExecPinName(FromPin) || IsExecPinName(TargetPin))
					{
						TryWireExec(Spec.Node, *TargetPtr, FromPin);
					}
					else
					{
						TryWireData(Spec.Node, FromPin, *TargetPtr, TargetPin);
					}
				}
			}
		}
	}

	void WireFromInputs(const TArray<FNodeSpec>& Specs, const TMap<FString, UK2Node*>& Map)
	{
		for (const FNodeSpec& Spec : Specs)
		{
			if (!Spec.Node || !Spec.Inputs.IsValid())
			{
				continue;
			}
			for (const auto& Pair : Spec.Inputs->Values)
			{
				const FString Key = Pair.Key;
				const TSharedPtr<FJsonValue> Val = Pair.Value;
				if (!Val.IsValid() || Val->Type != EJson::String)
				{
					continue;
				}
				const bool bExecKey = Key.StartsWith(TEXT("exec")) || Key.Equals(TEXT("execute"), ESearchCase::IgnoreCase);
				FString FromId, FromPin;
				ParseRef(Val->AsString(), FromId, FromPin);
				if (!bExecKey && !FromId.StartsWith(TEXT("node_")))
				{
					continue;
				}
				UK2Node* const* FromPtr = Map.Find(FromId);
				if (!FromPtr || !*FromPtr)
				{
					continue;
				}
				if (bExecKey || IsExecPinName(FromPin))
				{
					TryWireExec(*FromPtr, Spec.Node, FromPin);
				}
				else
				{
					TryWireData(*FromPtr, FromPin, Spec.Node, Key);
				}
			}
		}
	}
} // namespace PygenesisBp

FPygenesisBpApplyResult FPygenesisBpLiteApplier::ApplyFromJsonString(const FString& JsonString)
{
	TSharedPtr<FJsonObject> Obj;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonString);
	if (!FJsonSerializer::Deserialize(Reader, Obj) || !Obj.IsValid())
	{
		return {false, TEXT("JSON BP-Lite invalido"), TEXT("")};
	}
	return ApplyFromJsonObject(Obj);
}

FPygenesisBpApplyResult FPygenesisBpLiteApplier::ApplyFromJsonObject(const TSharedPtr<FJsonObject>& Graph)
{
	using namespace PygenesisBp;

	FPygenesisBpApplyResult Result;
	if (!Graph.IsValid())
	{
		Result.Message = TEXT("Grafo nulo");
		return Result;
	}

	FString GraphName;
	Graph->TryGetStringField(TEXT("graph_name"), GraphName);
	if (GraphName.IsEmpty())
	{
		GraphName = TEXT("Pygenesis_BP");
	}
	GraphName = GraphName.Replace(TEXT(" "), TEXT("_"));

	const TArray<TSharedPtr<FJsonValue>>* NodesPtr = nullptr;
	if (!Graph->TryGetArrayField(TEXT("nodes"), NodesPtr) || NodesPtr == nullptr || NodesPtr->Num() == 0)
	{
		Result.Message = TEXT("nodes vacio");
		return Result;
	}

	const bool bCharacter = WantsCharacter(*NodesPtr);
	UClass* ParentClass = bCharacter ? ACharacter::StaticClass() : AActor::StaticClass();

	UBlueprintFactory* Factory = NewObject<UBlueprintFactory>();
	Factory->ParentClass = ParentClass;

	const FString PackagePath = TEXT("/Game/Pygenesis");
	FString AssetName = GraphName;
	FString PackageName = PackagePath / AssetName;
	if (FPackageName::DoesPackageExist(PackageName))
	{
		AssetName = GraphName + TEXT("_Pygen");
		PackageName = PackagePath / AssetName;
	}

	IAssetTools& AssetTools = FModuleManager::LoadModuleChecked<FAssetToolsModule>("AssetTools").Get();
	UObject* NewAsset = AssetTools.CreateAsset(AssetName, PackagePath, UBlueprint::StaticClass(), Factory);
	UBlueprint* BP = Cast<UBlueprint>(NewAsset);
	if (!BP)
	{
		Result.Message = TEXT("No se pudo crear el Blueprint");
		return Result;
	}

	UEdGraph* EventGraph = FBlueprintEditorUtils::FindEventGraph(BP);
	if (!EventGraph)
	{
		Result.Message = TEXT("Blueprint sin Event Graph");
		return Result;
	}

	// Quitar stubs BeginPlay/Tick/Overlap que UE mete solos al crear Actor/Character
	ClearAutoGeneratedDefaultEvents(EventGraph);

	TArray<FNodeSpec> Specs;
	TMap<FString, UK2Node*> NodeMap;
	int32 Index = 0;
	int32 NativeEvents = 0;
	int32 CallNodes = 0;

	for (const TSharedPtr<FJsonValue>& Val : *NodesPtr)
	{
		const TSharedPtr<FJsonObject> N = Val.IsValid() ? Val->AsObject() : nullptr;
		if (!N.IsValid())
		{
			continue;
		}

		FNodeSpec Spec;
		N->TryGetStringField(TEXT("id"), Spec.Id);
		N->TryGetStringField(TEXT("type"), Spec.Type);
		N->TryGetStringField(TEXT("name"), Spec.Name);
		if (Spec.Id.IsEmpty())
		{
			Spec.Id = FString::Printf(TEXT("node_%02d"), Index + 1);
		}
		if (Spec.Id.IsNumeric())
		{
			Spec.Id = FString::Printf(TEXT("node_%02d"), FCString::Atoi(*Spec.Id));
		}

		const TSharedPtr<FJsonObject>* InObj = nullptr;
		const TSharedPtr<FJsonObject>* OutObj = nullptr;
		if (N->TryGetObjectField(TEXT("inputs"), InObj) && InObj)
		{
			Spec.Inputs = *InObj;
		}
		if (N->TryGetObjectField(TEXT("outputs"), OutObj) && OutObj)
		{
			Spec.Outputs = *OutObj;
		}

		const int32 PosX = 150 + (Index % 4) * 350;
		const int32 PosY = 80 + (Index / 4) * 240;
		++Index;

		const FString TypeLower = Spec.Type.ToLower();
		UK2Node* Created = nullptr;

		FName NativeEventName;
		UClass* EventOwner = nullptr;
		if (ResolveNativeEvent(Spec.Type, Spec.Name, NativeEventName, EventOwner))
		{
			Created = SpawnNativeEvent(EventGraph, ParentClass, NativeEventName, EventOwner, PosX, PosY);
			++NativeEvents;
		}
		else if (IsInputKey(Spec.Type, Spec.Name)
			|| Spec.Name.Equals(TEXT("SpaceBar"), ESearchCase::IgnoreCase)
			|| TypeLower.Contains(TEXT("inputkey"))
			|| TypeLower.Contains(TEXT("inputaction")))
		{
			// InputKey (incluye dialecto Ollama Event_InputAction_*); no Enhanced Input asset
			FString KeyName = Spec.Name;
			if (KeyName.IsEmpty() || KeyName.Equals(TEXT("InputKey"), ESearchCase::IgnoreCase)
				|| KeyName.Contains(TEXT("Node"), ESearchCase::IgnoreCase)
				|| KeyName.Contains(TEXT("InputAction"), ESearchCase::IgnoreCase))
			{
				KeyName = Spec.Type; // p.ej. Event_InputAction_F
			}
			Created = SpawnInputKey(EventGraph, ExtractInputKey(KeyName), PosX, PosY);
			++NativeEvents;
		}
		else if (IsInputAction(Spec.Type, Spec.Name)
			|| (TypeLower.Contains(TEXT("input")) && !TypeLower.Contains(TEXT("inputkey"))
				&& !TypeLower.Contains(TEXT("inputaction"))))
		{
			Created = SpawnInputAction(EventGraph, ExtractInputActionName(Spec.Name), PosX, PosY);
			++NativeEvents;
		}
		else if (TypeLower.Contains(TEXT("branch")) || Spec.Name.ToLower().Contains(TEXT("branch")))
		{
			UK2Node_IfThenElse* Branch = NewObject<UK2Node_IfThenElse>(EventGraph);
			StampNewNode(Branch);
			Branch->AllocateDefaultPins();
			Branch->NodePosX = PosX;
			Branch->NodePosY = PosY;
			EventGraph->AddNode(Branch, false, false);
			// Sin esto el pin Condition queda en false y en PIE siempre va por el else
			ApplyDefaultsFromInputs(Branch, Spec.Inputs, TEXT("Branch"));
			Created = Branch;
		}
		else if (TypeLower.Contains(TEXT("event")) || TypeLower.Contains(TEXT("trigger")))
		{
			// Evento no reconocido como nativo → CustomEvent con nombre limpio
			FString CustomName = Spec.Name.IsEmpty() ? TEXT("PygenesisEvent") : Spec.Name;
			// Evitar nombres que parecen nativos deshabilitados
			if (Compact(CustomName).Contains(TEXT("eventtick")) || Compact(CustomName).Contains(TEXT("beginoverlap")))
			{
				// Reintentar como nativo forzando Receive*
				if (Compact(CustomName).Contains(TEXT("tick")))
				{
					Created = SpawnNativeEvent(EventGraph, ParentClass, FName(TEXT("ReceiveTick")), AActor::StaticClass(), PosX, PosY);
					++NativeEvents;
				}
				else if (Compact(CustomName).Contains(TEXT("overlap")))
				{
					Created = SpawnNativeEvent(EventGraph, ParentClass, FName(TEXT("ReceiveActorBeginOverlap")), AActor::StaticClass(), PosX, PosY);
					++NativeEvents;
				}
			}
			if (!Created)
			{
				Created = SpawnCustomEvent(EventGraph, CustomName, PosX, PosY);
			}
		}
		else
		{
			const FString FuncHint = Spec.Name.IsEmpty() ? Spec.Type : Spec.Name;
			const FString HintCompact = Compact(FuncHint);
			// AIMoveTo del menú admite Destination como literal. Simple Move to Location no.
			const bool bAiMoveToLocation = HintCompact.Contains(TEXT("aimoveto"))
				&& !HintCompact.Contains(TEXT("actor"));
			if (bAiMoveToLocation)
			{
				UK2Node_AIMoveTo* Move = NewObject<UK2Node_AIMoveTo>(EventGraph);
				StampNewNode(Move);
				Move->AllocateDefaultPins();
				Move->NodePosX = PosX;
				Move->NodePosY = PosY;
				EventGraph->AddNode(Move, false, false);
				ApplyDefaultsFromInputs(Move, Spec.Inputs, TEXT("AIMoveTo"));
				WireSelfToPin(EventGraph, Move, TEXT("Pawn"), PosX - 280, PosY + 80);
				Created = Move;
				++CallNodes;
			}
			if (!Created)
			{
				UFunction* Func = ResolveFunction(FuncHint, ParentClass);
				if (!Func && !Spec.Type.IsEmpty() && Spec.Type != FuncHint)
				{
					Func = ResolveFunction(Spec.Type, ParentClass);
				}
				if (Func)
				{
					UK2Node_CallFunction* Call = NewObject<UK2Node_CallFunction>(EventGraph);
					StampNewNode(Call);
					Call->SetFromFunction(Func);
					Call->AllocateDefaultPins();
					Call->NodePosX = PosX;
					Call->NodePosY = PosY;
					EventGraph->AddNode(Call, false, false);
					Created = Call;
					++CallNodes;
					ApplyDefaultsFromInputs(Call, Spec.Inputs, Func->GetName());
					if (Func->GetName().Contains(TEXT("PrintString")))
					{
						if (UEdGraphPin* Msg = Call->FindPin(TEXT("InString")))
						{
							if (Msg->DefaultValue.IsEmpty() && !Spec.Name.IsEmpty())
							{
								Msg->DefaultValue = Spec.Name;
							}
						}
					}
				}
				else
				{
					UE_LOG(LogTemp, Warning,
						TEXT("Pygenesis BP-Lite: nodo omitido id=%s type=%s name=%s"),
						*Spec.Id, *Spec.Type, *Spec.Name);
				}
			}
		}

		Spec.Node = Created;
		if (Created)
		{
			NodeMap.Add(Spec.Id, Created);
		}
		Specs.Add(Spec);
	}

	// 1) Cableado declarado en JSON
	WireFromOutputs(Specs, NodeMap);
	WireFromInputs(Specs, NodeMap);

	// 2) Si no hay ningun cable exec, cadena secuencial como fallback util
	bool bAnyExecLink = false;
	for (const auto& Pair : NodeMap)
	{
		UK2Node* Node = Pair.Value;
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (Pin && Pin->Direction == EGPD_Output && Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_Exec && Pin->LinkedTo.Num() > 0)
			{
				bAnyExecLink = true;
				break;
			}
		}
		if (bAnyExecLink)
		{
			break;
		}
	}
	if (!bAnyExecLink)
	{
		UK2Node* Prev = nullptr;
		for (const FNodeSpec& Spec : Specs)
		{
			if (!Spec.Node)
			{
				continue;
			}
			if (Prev)
			{
				TryWireExec(Prev, Spec.Node);
			}
			Prev = Spec.Node;
		}
	}

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
	FKismetEditorUtilities::CompileBlueprint(BP);

	// InputKey/InputAction en un Actor del nivel NO reciben teclado sin Auto Receive Input.
	const bool bHasInputNodes = NativeEvents > 0 && [&Specs]()
	{
		for (const FNodeSpec& S : Specs)
		{
			const FString Blob = Compact(S.Type + S.Name);
			if (Blob.Contains(TEXT("input")) || Blob.Contains(TEXT("space")) || Blob.Len() == 1)
			{
				return true;
			}
			if (Cast<UK2Node_InputKey>(S.Node) || Cast<UK2Node_InputAction>(S.Node))
			{
				return true;
			}
		}
		return false;
	}();
	if (bHasInputNodes && BP->GeneratedClass)
	{
		if (AActor* CDO = Cast<AActor>(BP->GeneratedClass->GetDefaultObject()))
		{
			CDO->AutoReceiveInput = EAutoReceiveInput::Player0;
			CDO->MarkPackageDirty();
			UE_LOG(LogPygenesisBp, Display, TEXT("AutoReceiveInput=Player0 en %s"), *BP->GetName());
		}
	}

	UPackage* Package = BP->GetOutermost();
	const FString PackageFilename = FPackageName::LongPackageNameToFilename(
		Package->GetName(), FPackageName::GetAssetPackageExtension());
	FSavePackageArgs SaveArgs;
	SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
	UPackage::SavePackage(Package, BP, *PackageFilename, SaveArgs);

	Result.bOk = true;
	Result.AssetPath = PackageName;
	Result.Message = FString::Printf(
		TEXT("Blueprint %s | nodos=%d (entradas=%d, llamadas=%d). AutoReceiveInput=%s."),
		*PackageName,
		NodeMap.Num(),
		NativeEvents,
		CallNodes,
		bHasInputNodes ? TEXT("Player0") : TEXT("n/a"));
	UE_LOG(LogPygenesisBp, Display, TEXT("%s"), *Result.Message);
	return Result;
}
