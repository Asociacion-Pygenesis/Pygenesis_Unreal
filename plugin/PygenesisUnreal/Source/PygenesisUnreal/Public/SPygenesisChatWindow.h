#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "PygenesisBridgeClient.h"
#include "Containers/Ticker.h"

class SMultiLineEditableTextBox;
class SEditableTextBox;
class STextBlock;

class SPygenesisChatWindow : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SPygenesisChatWindow) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
	virtual ~SPygenesisChatWindow() override;

private:
	TSharedPtr<FPygenesisBridgeClient> Client;
	TSharedPtr<SMultiLineEditableTextBox> TranscriptBox;
	TSharedPtr<SEditableTextBox> PromptBox;
	TSharedPtr<STextBlock> StatusText;

	/** Última respuesta del chat (puede ser solo la explicación tras un «sí»). */
	FString LastAssistantReply;
	/** Última respuesta con JSON BP-Lite o Lighting-Spec (para Aplicar tras la explicación). */
	FString LastStructuredReply;
	/** Petición que generó LastStructuredReply: el backend la necesita al normalizar. */
	FString LastStructuredPrompt;
	/** Último prompt enviado (aún sin respuesta estructurada). */
	FString LastUserPrompt;
	FString TranscriptBeforeStream;
	/** Texto objetivo del stream (llega a saltos desde el poll). */
	FString StreamTargetText;
	/** Cuántos caracteres del target ya se han revelado (typewriter). */
	int32 StreamVisibleChars = 0;
	bool bStreamingReply = false;
	/** El usuario pulsó Detener: el texto queda, el estado no dice «Listo». */
	bool bUserStopped = false;
	/** true = job terminó; el ticker acelera hasta pillar el texto y luego cierra. */
	bool bFinalizePending = false;
	bool bFinalizeOk = true;
	bool bBusy = false;
	FTSTicker::FDelegateHandle TypewriterTickerHandle;

	FReply OnSendClicked();
	FReply OnStopClicked();
	FReply OnClearChatClicked();
	FReply OnHealthClicked();
	FReply OnStartBackendClicked();
	FReply OnApplyBpLiteClicked();
	FReply OnApplyLightingClicked();
	void AppendTranscript(const FString& Role, const FString& Text);
	void BeginStreamingReply();
	void UpdateStreamingReply(const FString& Partial);
	void EndStreamingReply(const FString& FinalText, bool bOk);
	void RefreshStreamingDisplay();
	void StartTypewriterTicker();
	void StopTypewriterTicker();
	bool TickTypewriter(float DeltaTime);
	void SetStatus(const FString& Text);
	void SetBusy(bool bInBusy);
	void PollHealthAfterStart(int32 AttemptsLeft);
	/** Guarda reply para chat; si trae JSON BP/Lighting, también para Aplicar. */
	void RememberAssistantReply(const FString& Reply);
	const FString& GetTextForApply() const;
};
