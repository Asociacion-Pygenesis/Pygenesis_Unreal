#include "PygenesisUnrealModule.h"
#include "SPygenesisChatWindow.h"

#include "ToolMenus.h"
#include "WorkspaceMenuStructure.h"
#include "WorkspaceMenuStructureModule.h"
#include "Framework/Docking/TabManager.h"
#include "Widgets/Docking/SDockTab.h"

#define LOCTEXT_NAMESPACE "FPygenesisUnrealModule"

const FName FPygenesisUnrealModule::ChatTabName(TEXT("PygenesisUnrealChat"));

void FPygenesisUnrealModule::StartupModule()
{
	FGlobalTabmanager::Get()->RegisterNomadTabSpawner(
		ChatTabName,
		FOnSpawnTab::CreateRaw(this, &FPygenesisUnrealModule::SpawnChatTab))
		.SetDisplayName(LOCTEXT("TabTitle", "Pygenesis Unreal"))
		.SetTooltipText(LOCTEXT("TabTooltip", "Asistente IA local (puente GGUF en localhost:8000)"))
		.SetGroup(WorkspaceMenu::GetMenuStructure().GetToolsCategory());

	UToolMenus::RegisterStartupCallback(
		FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FPygenesisUnrealModule::RegisterMenus));
}

void FPygenesisUnrealModule::ShutdownModule()
{
	UToolMenus::UnRegisterStartupCallback(this);
	UToolMenus::UnregisterOwner(this);
	FGlobalTabmanager::Get()->UnregisterNomadTabSpawner(ChatTabName);
}

void FPygenesisUnrealModule::RegisterMenus()
{
	FToolMenuOwnerScoped OwnerScoped(this);
	UToolMenu* Menu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu.Window");
	FToolMenuSection& Section = Menu->FindOrAddSection("WindowLayout");
	Section.AddMenuEntry(
		"PygenesisUnrealOpen",
		LOCTEXT("OpenChat", "Pygenesis Unreal"),
		LOCTEXT("OpenChatTooltip", "Abre el asistente IA local (requiere puente en localhost:8000)."),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateRaw(this, &FPygenesisUnrealModule::OpenChatWindow)));
}

void FPygenesisUnrealModule::OpenChatWindow()
{
	FGlobalTabmanager::Get()->TryInvokeTab(ChatTabName);
}

TSharedRef<SDockTab> FPygenesisUnrealModule::SpawnChatTab(const FSpawnTabArgs& Args)
{
	return SNew(SDockTab)
		.TabRole(ETabRole::NomadTab)
		[
			SNew(SPygenesisChatWindow)
		];
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FPygenesisUnrealModule, PygenesisUnreal)
