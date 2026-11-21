using UnrealBuildTool;

public class PygenesisUnreal : ModuleRules
{
	public PygenesisUnreal(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore"
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"Slate",
			"SlateCore",
			"UnrealEd",
			"ToolMenus",
			"EditorStyle",
			"EditorWidgets",
			"WorkspaceMenuStructure",
			"HTTP",
			"Json",
			"JsonUtilities",
			"AssetTools",
			"AssetRegistry",
			"BlueprintGraph",
			"Kismet",
			"KismetCompiler",
			"GraphEditor",
			"InputCore",
			"Projects",
			"AIModule",
			"AIGraph"
		});

		if (Target.Platform == UnrealTargetPlatform.Win64)
		{
			PublicSystemLibraries.Add("shell32.lib");
		}
	}
}
