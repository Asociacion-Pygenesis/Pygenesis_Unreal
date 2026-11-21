#pragma once

#include "CoreMinimal.h"

struct FPygenesisLaunchResult
{
	bool bOk = false;
	bool bAlreadyRunning = false;
	FString Message;
	FString ScriptPath;
};

/**
 * Arranca el puente FastAPI desde el Editor (PowerShell + start_backend.ps1).
 * Resuelve el script en %LOCALAPPDATA%\PygenesisUnreal o vía bridge.env.
 */
class FPygenesisBackendLauncher
{
public:
	/** Ruta al .ps1 de arranque, o vacío si no se encuentra. */
	static FString ResolveStartScript();

	/** Lanza el backend en segundo plano (ventana PowerShell minimizada). */
	static FPygenesisLaunchResult StartBackendDetached();
};
