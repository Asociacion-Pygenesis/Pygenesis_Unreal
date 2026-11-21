#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"
#include "Widgets/Docking/SDockTab.h"

class FPygenesisUnrealModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

private:
	static const FName ChatTabName;

	void RegisterMenus();
	void OpenChatWindow();
	TSharedRef<SDockTab> SpawnChatTab(const FSpawnTabArgs& Args);
};
