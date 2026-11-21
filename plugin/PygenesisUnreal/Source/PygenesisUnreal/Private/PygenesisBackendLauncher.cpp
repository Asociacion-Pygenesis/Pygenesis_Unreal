#include "PygenesisBackendLauncher.h"

#include "HAL/FileManager.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/PlatformProcess.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

#if PLATFORM_WINDOWS
#include "Windows/AllowWindowsPlatformTypes.h"
#include <shellapi.h>
#include "Windows/HideWindowsPlatformTypes.h"
#endif

DEFINE_LOG_CATEGORY_STATIC(LogPygenesisLaunch, Log, All);

namespace PygenesisLaunch
{
	FString LocalAppData()
	{
		return FPlatformMisc::GetEnvironmentVariable(TEXT("LOCALAPPDATA"));
	}

	void AppendLaunchLog(const FString& Line)
	{
		const FString LogDir = FPaths::Combine(LocalAppData(), TEXT("PygenesisUnreal"), TEXT("logs"));
		IFileManager::Get().MakeDirectory(*LogDir, true);
		const FString LaunchLogFile = FPaths::Combine(LogDir, TEXT("editor_launch.log"));
		const FString Stamp = FDateTime::Now().ToString(TEXT("%Y-%m-%d %H:%M:%S"));
		FFileHelper::SaveStringToFile(
			FString::Printf(TEXT("[%s] %s\n"), *Stamp, *Line),
			*LaunchLogFile,
			FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,
			&IFileManager::Get(),
			EFileWrite::FILEWRITE_Append);
	}

	FString ReadBridgeEnvValue(const FString& Key)
	{
		const FString EnvPath = FPaths::Combine(LocalAppData(), TEXT("PygenesisUnreal"), TEXT("bridge.env"));
		FString Contents;
		if (!FFileHelper::LoadFileToString(Contents, *EnvPath))
		{
			return FString();
		}
		TArray<FString> Lines;
		Contents.ParseIntoArrayLines(Lines, false);
		for (const FString& Line : Lines)
		{
			FString Trimmed = Line.TrimStartAndEnd();
			if (Trimmed.IsEmpty() || Trimmed.StartsWith(TEXT("#")))
			{
				continue;
			}
			FString Name, Value;
			if (Trimmed.Split(TEXT("="), &Name, &Value))
			{
				if (Name.TrimStartAndEnd().Equals(Key, ESearchCase::IgnoreCase))
				{
					return Value.TrimStartAndEnd();
				}
			}
		}
		return FString();
	}

	FString DeriveStartFromPython(const FString& PythonExe)
	{
		if (PythonExe.IsEmpty() || !FPaths::FileExists(PythonExe))
		{
			return FString();
		}
		FString Dir = FPaths::GetPath(PythonExe); // Scripts
		Dir = FPaths::GetPath(Dir);               // .venv or runtime
		Dir = FPaths::GetPath(Dir);               // training or PygenesisUnreal
		const FString CandidateA = FPaths::Combine(Dir, TEXT("backend"), TEXT("scripts"), TEXT("start_backend.ps1"));
		if (FPaths::FileExists(CandidateA))
		{
			return FPaths::ConvertRelativePathToFull(CandidateA);
		}
		const FString CandidateB = FPaths::Combine(Dir, TEXT("app"), TEXT("backend"), TEXT("scripts"), TEXT("start_backend.ps1"));
		if (FPaths::FileExists(CandidateB))
		{
			return FPaths::ConvertRelativePathToFull(CandidateB);
		}
		const FString RepoRoot = FPaths::GetPath(Dir);
		const FString CandidateC = FPaths::Combine(RepoRoot, TEXT("backend"), TEXT("scripts"), TEXT("start_backend.ps1"));
		if (FPaths::FileExists(CandidateC))
		{
			return FPaths::ConvertRelativePathToFull(CandidateC);
		}
		return FString();
	}

	FString PowerShellExe()
	{
		const FString SystemRoot = FPlatformMisc::GetEnvironmentVariable(TEXT("SystemRoot"));
		const FString Candidate = FPaths::Combine(SystemRoot, TEXT("System32"), TEXT("WindowsPowerShell"), TEXT("v1.0"), TEXT("powershell.exe"));
		if (FPaths::FileExists(Candidate))
		{
			return Candidate;
		}
		return TEXT("powershell.exe");
	}

	FString CmdExe()
	{
		const FString SystemRoot = FPlatformMisc::GetEnvironmentVariable(TEXT("SystemRoot"));
		const FString Candidate = FPaths::Combine(SystemRoot, TEXT("System32"), TEXT("cmd.exe"));
		if (FPaths::FileExists(Candidate))
		{
			return Candidate;
		}
		return TEXT("cmd.exe");
	}

	/** Escribe un .cmd que arranca el .ps1 en consola nueva (sobrevive si Unreal cierra hijos). */
	FString EnsureLaunchCmd(const FString& Ps1Path)
	{
		const FString Home = FPaths::Combine(LocalAppData(), TEXT("PygenesisUnreal"));
		IFileManager::Get().MakeDirectory(*Home, true);
		const FString CmdPath = FPaths::Combine(Home, TEXT("Launch-Backend.cmd"));
		const FString Ps1Norm = FPaths::ConvertRelativePathToFull(Ps1Path);
		const FString PsExe = PowerShellExe();
		// No usar %date%/%time% dentro de Printf (UE lo interpreta como formato).
		FString Body;
		Body += TEXT("@echo off\r\n");
		Body += TEXT("title Pygenesis Backend\r\n");
		Body += TEXT("cd /d \"%LOCALAPPDATA%\\PygenesisUnreal\"\r\n");
		Body += TEXT("echo Launch-Backend.cmd started>> \"%LOCALAPPDATA%\\PygenesisUnreal\\logs\\editor_launch.log\"\r\n");
		Body += FString::Printf(
			TEXT("\"%s\" -NoProfile -ExecutionPolicy Bypass -File \"%s\"\r\n"),
			*PsExe,
			*Ps1Norm);
		FFileHelper::SaveStringToFile(Body, *CmdPath, FFileHelper::EEncodingOptions::ForceAnsi);
		return CmdPath;
	}

	bool LaunchViaShellExecute(const FString& CmdPath)
	{
#if PLATFORM_WINDOWS
		const FString FullCmd = FPaths::ConvertRelativePathToFull(CmdPath);
		HINSTANCE Inst = ShellExecuteW(
			nullptr,
			L"open",
			*FullCmd,
			nullptr,
			nullptr,
			SW_SHOWMINNOACTIVE);
		const INT_PTR Code = reinterpret_cast<INT_PTR>(Inst);
		AppendLaunchLog(FString::Printf(TEXT("ShellExecuteW(%s) -> %lld"), *FullCmd, static_cast<long long>(Code)));
		// ShellExecute: >32 = success
		return Code > 32;
#else
		return false;
#endif
	}

	bool LaunchViaCmdStart(const FString& CmdPath)
	{
		const FString FullCmd = FPaths::ConvertRelativePathToFull(CmdPath);
		const FString Exe = CmdExe();
		// start "" → nueva consola independiente del Editor
		const FString Args = FString::Printf(
			TEXT("/C start \"PygenesisBackend\" /MIN cmd.exe /C \"%s\""),
			*FullCmd);

		AppendLaunchLog(FString::Printf(TEXT("CreateProc %s %s"), *Exe, *Args));

		FProcHandle Proc = FPlatformProcess::CreateProc(
			*Exe,
			*Args,
			true,
			false,
			false,
			nullptr,
			0,
			*FPaths::GetPath(FullCmd),
			nullptr);

		if (!Proc.IsValid())
		{
			AppendLaunchLog(TEXT("CreateProc INVALID"));
			return false;
		}
		FPlatformProcess::CloseProc(Proc);
		AppendLaunchLog(TEXT("CreateProc OK (detached)"));
		return true;
	}
}

FString FPygenesisBackendLauncher::ResolveStartScript()
{
	using namespace PygenesisLaunch;

	TArray<FString> Candidates;

	const FString Home = FPaths::Combine(LocalAppData(), TEXT("PygenesisUnreal"));
	Candidates.Add(FPaths::Combine(Home, TEXT("Start-Backend.ps1")));
	Candidates.Add(FPaths::Combine(Home, TEXT("app"), TEXT("backend"), TEXT("scripts"), TEXT("start_backend.ps1")));
	Candidates.Add(FPaths::Combine(Home, TEXT("backend"), TEXT("scripts"), TEXT("start_backend.ps1")));

	const FString Explicit = ReadBridgeEnvValue(TEXT("PYGENESIS_START_SCRIPT"));
	if (!Explicit.IsEmpty())
	{
		Candidates.Insert(Explicit, 0);
	}

	const FString FromPy = DeriveStartFromPython(ReadBridgeEnvValue(TEXT("PYGENESIS_PYTHON")));
	if (!FromPy.IsEmpty())
	{
		Candidates.Add(FromPy);
	}

	if (TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("PygenesisUnreal")))
	{
		Candidates.Add(FPaths::Combine(Plugin->GetBaseDir(), TEXT("Resources"), TEXT("Start-Backend.ps1")));
	}

	for (const FString& Path : Candidates)
	{
		if (!Path.IsEmpty() && FPaths::FileExists(Path))
		{
			return FPaths::ConvertRelativePathToFull(Path);
		}
	}
	return FString();
}

FPygenesisLaunchResult FPygenesisBackendLauncher::StartBackendDetached()
{
	using namespace PygenesisLaunch;

	FPygenesisLaunchResult Result;
	Result.ScriptPath = ResolveStartScript();
	AppendLaunchLog(FString::Printf(TEXT("ResolveStartScript -> %s"),
		Result.ScriptPath.IsEmpty() ? TEXT("(empty)") : *Result.ScriptPath));

	if (Result.ScriptPath.IsEmpty())
	{
		Result.Message = TEXT(
			"No se encontro start_backend.ps1. "
			"Esperado en %LOCALAPPDATA%\\PygenesisUnreal\\Start-Backend.ps1");
		return Result;
	}

	const FString CmdPath = EnsureLaunchCmd(Result.ScriptPath);
	Result.ScriptPath = CmdPath;

	bool bLaunched = LaunchViaShellExecute(CmdPath);
	if (!bLaunched)
	{
		AppendLaunchLog(TEXT("ShellExecute fallo; reintento CreateProc/cmd start"));
		bLaunched = LaunchViaCmdStart(CmdPath);
	}

	if (!bLaunched)
	{
		Result.Message = FString::Printf(
			TEXT("No se pudo lanzar el backend. Script=%s. Revisa %%LOCALAPPDATA%%\\PygenesisUnreal\\logs\\editor_launch.log"),
			*CmdPath);
		return Result;
	}

	Result.bOk = true;
	Result.Message = FString::Printf(
		TEXT("Backend lanzado via %s. Esperando carga del modelo..."),
		*CmdPath);
	UE_LOG(LogPygenesisLaunch, Display, TEXT("%s"), *Result.Message);
	return Result;
}
