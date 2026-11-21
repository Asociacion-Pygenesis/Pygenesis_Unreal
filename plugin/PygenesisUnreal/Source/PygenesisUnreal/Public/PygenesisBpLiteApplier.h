#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

struct FPygenesisBpApplyResult
{
	bool bOk = false;
	FString Message;
	FString AssetPath;
};

/**
 * Crea un Blueprint en /Game/Pygenesis y monta el grafo BP-Lite:
 * eventos nativos (Tick, BeginPlay, Overlap...), Branch, CallFunction,
 * cableado exec segun inputs/outputs y defaults de pines de datos.
 */
class FPygenesisBpLiteApplier
{
public:
	static FPygenesisBpApplyResult ApplyFromJsonObject(const TSharedPtr<FJsonObject>& Graph);
	static FPygenesisBpApplyResult ApplyFromJsonString(const FString& JsonString);
};
