#include "SPygenesisChatWindow.h"
#include "PygenesisBackendLauncher.h"
#include "PygenesisBpLiteApplier.h"
#include "PygenesisLightingApplier.h"

#include "Editor.h"
#include "Engine/World.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SMultiLineEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"
#include "Styling/AppStyle.h"
#include "Framework/Notifications/NotificationManager.h"
#include "Widgets/Notifications/SNotificationList.h"

#define LOCTEXT_NAMESPACE "SPygenesisChatWindow"

void SPygenesisChatWindow::Construct(const FArguments& InArgs)
{
	Client = MakeShared<FPygenesisBridgeClient>();

	ChildSlot
	[
		SNew(SBorder)
		.BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder"))
		.Padding(8.0f)
		[
			SNew(SVerticalBox)

			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(0, 0, 0, 6)
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.FillWidth(1.0f)
				.VAlign(VAlign_Center)
				[
					SAssignNew(StatusText, STextBlock)
					.Text(LOCTEXT("StatusDefault", "Puente: sin comprobar (127.0.0.1:8000)"))
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.Padding(8, 0, 0, 0)
				[
					SNew(SButton)
					.Text(LOCTEXT("StartBackendBtn", "Iniciar Backend"))
					.ToolTipText(LOCTEXT("StartBackendTip", "Arranca el puente FastAPI (PowerShell) si no esta en marcha"))
					.IsEnabled_Lambda([this]() { return !bBusy; })
					.OnClicked(this, &SPygenesisChatWindow::OnStartBackendClicked)
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.Padding(8, 0, 0, 0)
				[
					SNew(SButton)
					.Text(LOCTEXT("HealthBtn", "Health"))
					.OnClicked(this, &SPygenesisChatWindow::OnHealthClicked)
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.Padding(8, 0, 0, 0)
				[
					SNew(SButton)
					.Text(LOCTEXT("ApplyBtn", "Aplicar BP-Lite"))
					.ToolTipText(LOCTEXT("ApplyTip", "Extrae el JSON BP-Lite de la ultima respuesta y crea un Blueprint en /Game/Pygenesis"))
					.IsEnabled_Lambda([this]() { return !bBusy && !GetTextForApply().IsEmpty() && GetTextForApply().Contains(TEXT("graph_name")); })
					.OnClicked(this, &SPygenesisChatWindow::OnApplyBpLiteClicked)
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.Padding(8, 0, 0, 0)
				[
					SNew(SButton)
					.Text(LOCTEXT("ApplyLightBtn", "Aplicar Lighting"))
					.ToolTipText(LOCTEXT("ApplyLightTip", "Extrae Lighting-Spec de la ultima respuesta y aplica sol/fog/post-process al nivel"))
					.IsEnabled_Lambda([this]() { return !bBusy && !GetTextForApply().IsEmpty() && GetTextForApply().Contains(TEXT("environment_type")); })
					.OnClicked(this, &SPygenesisChatWindow::OnApplyLightingClicked)
				]
			]

			+ SVerticalBox::Slot()
			.FillHeight(1.0f)
			[
				SNew(SBorder)
				.BorderImage(FAppStyle::GetBrush("ToolPanel.DarkGroupBorder"))
				.Padding(4.0f)
				[
					SAssignNew(TranscriptBox, SMultiLineEditableTextBox)
					.IsReadOnly(true)
					.AutoWrapText(true)
					.Text(LOCTEXT(
						"Welcome",
						"Pygenesis Unreal — asistente local.\n"
						"1) Iniciar Backend (si hace falta) → Health\n"
						"2) Pide un Blueprint o una atmosfera/iluminacion\n"
						"3) Aplicar BP-Lite o Aplicar Lighting segun el JSON\n"
						"Detener corta la generacion y deja lo ya escrito. Limpiar vacia el chat.\n"))
				]
			]

			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(0, 8, 0, 0)
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.FillWidth(1.0f)
				[
					SAssignNew(PromptBox, SEditableTextBox)
					.HintText(LOCTEXT("PromptHint", "Pregunta sobre UE5..."))
					.OnTextCommitted_Lambda([this](const FText& /*Text*/, ETextCommit::Type CommitType)
					{
						if (CommitType == ETextCommit::OnEnter)
						{
							OnSendClicked();
						}
					})
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.Padding(8, 0, 0, 0)
				[
					SNew(SButton)
					.Text(LOCTEXT("SendBtn", "Enviar"))
					.IsEnabled_Lambda([this]() { return !bBusy; })
					.OnClicked(this, &SPygenesisChatWindow::OnSendClicked)
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.Padding(8, 0, 0, 0)
				[
					SNew(SButton)
					.Text(LOCTEXT("StopBtn", "Detener"))
					.ToolTipText(LOCTEXT("StopTip", "Corta el modelo y conserva en el chat lo que ya ha escrito"))
					.IsEnabled_Lambda([this]() { return bStreamingReply; })
					.OnClicked(this, &SPygenesisChatWindow::OnStopClicked)
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.Padding(8, 0, 0, 0)
				[
					SNew(SButton)
					.Text(LOCTEXT("ClearBtn", "Limpiar"))
					.ToolTipText(LOCTEXT("ClearTip", "Vacia el chat y la ultima respuesta. No para el backend"))
					.IsEnabled_Lambda([this]() { return !bBusy; })
					.OnClicked(this, &SPygenesisChatWindow::OnClearChatClicked)
				]
			]
		]
	];
}

void SPygenesisChatWindow::AppendTranscript(const FString& Role, const FString& Text)
{
	if (!TranscriptBox.IsValid())
	{
		return;
	}
	const FString Current = TranscriptBox->GetText().ToString();
	const FString Block = FString::Printf(TEXT("\n[%s]\n%s\n"), *Role, *Text);
	TranscriptBox->SetText(FText::FromString(Current + Block));
}

SPygenesisChatWindow::~SPygenesisChatWindow()
{
	StopTypewriterTicker();
}

void SPygenesisChatWindow::StartTypewriterTicker()
{
	if (TypewriterTickerHandle.IsValid())
	{
		return;
	}
	TypewriterTickerHandle = FTSTicker::GetCoreTicker().AddTicker(
		FTickerDelegate::CreateSP(this, &SPygenesisChatWindow::TickTypewriter),
		0.016f); // ~60 fps, revelado suave caracter a caracter
}

void SPygenesisChatWindow::StopTypewriterTicker()
{
	if (TypewriterTickerHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(TypewriterTickerHandle);
		TypewriterTickerHandle.Reset();
	}
}

void SPygenesisChatWindow::RefreshStreamingDisplay()
{
	if (!TranscriptBox.IsValid() || !bStreamingReply)
	{
		return;
	}
	const FString Visible = StreamTargetText.Left(StreamVisibleChars);
	TranscriptBox->SetText(FText::FromString(
		TranscriptBeforeStream + TEXT("\n[Pygenesis]\n") + Visible));
}

bool SPygenesisChatWindow::TickTypewriter(float /*DeltaTime*/)
{
	if (!bStreamingReply)
	{
		return false;
	}
	const int32 TargetLen = StreamTargetText.Len();
	if (StreamVisibleChars < TargetLen)
	{
		const int32 Backlog = TargetLen - StreamVisibleChars;
		// Seguimiento en vivo: si el poll adelanta mucho, acelerar (no quedarse a 2 chars/tick)
		// Al finalizar, aún más rápido para no alargar la espera.
		int32 Step;
		if (bFinalizePending)
		{
			Step = FMath::Clamp(Backlog / 2, 12, 64);
		}
		else
		{
			Step = FMath::Clamp(Backlog / 5, 3, 28);
		}
		StreamVisibleChars = FMath::Min(StreamVisibleChars + Step, TargetLen);
		RefreshStreamingDisplay();
		if (!bFinalizePending && !bUserStopped)
		{
			SetStatus(FString::Printf(TEXT("Generando... %d caracteres"), StreamVisibleChars));
		}
	}

	if (bFinalizePending && StreamVisibleChars >= StreamTargetText.Len())
	{
		const FString Role = bFinalizeOk ? TEXT("Pygenesis") : TEXT("Error");
		const FString FinalBody = StreamTargetText;
		if (TranscriptBox.IsValid())
		{
			TranscriptBox->SetText(FText::FromString(
				TranscriptBeforeStream + FString::Printf(TEXT("\n[%s]\n%s\n"), *Role, *FinalBody)));
		}
		if (bFinalizeOk && !FinalBody.IsEmpty())
		{
			RememberAssistantReply(FinalBody);
		}
		bStreamingReply = false;
		bFinalizePending = false;
		TranscriptBeforeStream.Reset();
		StreamTargetText.Reset();
		StreamVisibleChars = 0;
		if (bUserStopped)
		{
			SetStatus(TEXT("Generacion detenida. Lo escrito se conserva."));
		}
		else
		{
			SetStatus(bFinalizeOk
				? TEXT("Listo — Aplicar BP-Lite o Aplicar Lighting segun el JSON")
				: TEXT("Error en la consulta"));
		}
		bUserStopped = false;
		return false; // detener ticker
	}
	return true;
}

void SPygenesisChatWindow::BeginStreamingReply()
{
	if (!TranscriptBox.IsValid())
	{
		return;
	}
	TranscriptBeforeStream = TranscriptBox->GetText().ToString();
	StreamTargetText.Reset();
	StreamVisibleChars = 0;
	bFinalizePending = false;
	bFinalizeOk = true;
	bStreamingReply = true;
	RefreshStreamingDisplay();
	StartTypewriterTicker();
	SetStatus(TEXT("Generando... (primer token puede tardar)"));
}

void SPygenesisChatWindow::UpdateStreamingReply(const FString& Partial)
{
	if (!bStreamingReply || bFinalizePending)
	{
		return;
	}
	if (Partial.Len() < StreamTargetText.Len())
	{
		return;
	}
	// Espejo inmediato de lo que llega del poll (el typewriter solo “pulía” y
	// con parciales tardíos parecía que no había stream).
	StreamTargetText = Partial;
	StreamVisibleChars = StreamTargetText.Len();
	RefreshStreamingDisplay();
	if (!bUserStopped)
	{
		SetStatus(FString::Printf(TEXT("Generando... %d caracteres"), StreamTargetText.Len()));
	}
	StartTypewriterTicker();
}

void SPygenesisChatWindow::EndStreamingReply(const FString& FinalText, bool bOk)
{
	if (!TranscriptBox.IsValid())
	{
		StopTypewriterTicker();
		bStreamingReply = false;
		bFinalizePending = false;
		StreamTargetText.Reset();
		StreamVisibleChars = 0;
		return;
	}

	// Nunca sustituir lo ya streameado por vacío/(vacio)/texto sin JSON.
	FString ToShow = FinalText;
	if (bOk && !StreamTargetText.IsEmpty())
	{
		const bool bFinalEmpty = ToShow.IsEmpty() || ToShow.Equals(TEXT("(vacio)"));
		const bool bStreamHasJson = StreamTargetText.Contains(TEXT("graph_name"))
			|| StreamTargetText.Contains(TEXT("environment_type"));
		const bool bFinalHasJson = ToShow.Contains(TEXT("graph_name"))
			|| ToShow.Contains(TEXT("environment_type"));
		// El final normalizado manda aunque sea más corto que el stream.
		if (bFinalEmpty || (bStreamHasJson && !bFinalHasJson))
		{
			ToShow = StreamTargetText;
		}
	}

	if (!bStreamingReply)
	{
		AppendTranscript(bOk ? TEXT("Pygenesis") : TEXT("Error"), ToShow);
		if (bOk && !ToShow.IsEmpty())
		{
			RememberAssistantReply(ToShow);
		}
		return;
	}

	// No volcar de golpe: acelerar typewriter hasta el final y luego fijar el bloque.
	if (!ToShow.IsEmpty())
	{
		StreamTargetText = ToShow;
	}
	bFinalizeOk = bOk;
	bFinalizePending = true;
	SetStatus(TEXT("Terminando respuesta..."));
	StartTypewriterTicker();
}

void SPygenesisChatWindow::SetStatus(const FString& Text)
{
	if (StatusText.IsValid())
	{
		StatusText->SetText(FText::FromString(Text));
	}
}

void SPygenesisChatWindow::SetBusy(bool bInBusy)
{
	bBusy = bInBusy;
	// IsEnabled_Lambda de Aplicar/Enviar solo se reevalúa tras invalidar.
	Invalidate(EInvalidateWidgetReason::Layout | EInvalidateWidgetReason::Paint);
}

FReply SPygenesisChatWindow::OnHealthClicked()
{
	SetStatus(TEXT("Comprobando /health..."));
	TWeakPtr<SPygenesisChatWindow> WeakSelf = SharedThis(this);
	Client->CheckHealth(FOnPygenesisHealth::CreateLambda(
		[WeakSelf](bool bOk, const FString& Detail)
		{
			TSharedPtr<SPygenesisChatWindow> Self = WeakSelf.Pin();
			if (!Self.IsValid())
			{
				return;
			}
			Self->SetStatus(bOk
				? FString::Printf(TEXT("OK — %s"), *Detail)
				: FString::Printf(TEXT("Fallo — %s"), *Detail));
		}));
	return FReply::Handled();
}

void SPygenesisChatWindow::PollHealthAfterStart(int32 AttemptsLeft)
{
	TWeakPtr<SPygenesisChatWindow> WeakSelf = SharedThis(this);
	Client->CheckHealth(FOnPygenesisHealth::CreateLambda(
		[WeakSelf, AttemptsLeft](bool bOk, const FString& Detail)
		{
			TSharedPtr<SPygenesisChatWindow> Self = WeakSelf.Pin();
			if (!Self.IsValid())
			{
				return;
			}
			if (bOk)
			{
				Self->SetBusy(false);
				Self->SetStatus(FString::Printf(TEXT("Backend listo — %s"), *Detail));
				Self->AppendTranscript(TEXT("Sistema"), TEXT("Backend en marcha."));
				FNotificationInfo Info(FText::FromString(TEXT("Pygenesis backend listo")));
				Info.ExpireDuration = 4.0f;
				FSlateNotificationManager::Get().AddNotification(Info);
				return;
			}
			if (AttemptsLeft <= 0)
			{
				Self->SetBusy(false);
				Self->SetStatus(TEXT("Backend lanzado pero /health no responde aun. Revisa el log o pulsa Health."));
				return;
			}
			Self->SetStatus(FString::Printf(
				TEXT("Cargando modelo... (reintento health %d)"), AttemptsLeft));
			if (!GEditor)
			{
				Self->SetBusy(false);
				return;
			}
			UWorld* World = GEditor->GetEditorWorldContext().World();
			if (!World)
			{
				Self->SetBusy(false);
				return;
			}
			FTimerHandle Handle;
			World->GetTimerManager().SetTimer(
				Handle,
				FTimerDelegate::CreateLambda([WeakSelf, AttemptsLeft]()
				{
					if (TSharedPtr<SPygenesisChatWindow> S = WeakSelf.Pin())
					{
						S->PollHealthAfterStart(AttemptsLeft - 1);
					}
				}),
				2.0f,
				false);
		}));
}

FReply SPygenesisChatWindow::OnStartBackendClicked()
{
	SetBusy(true);
	SetStatus(TEXT("Comprobando si el backend ya esta activo..."));

	TWeakPtr<SPygenesisChatWindow> WeakSelf = SharedThis(this);
	Client->CheckHealth(FOnPygenesisHealth::CreateLambda(
		[WeakSelf](bool bOk, const FString& Detail)
		{
			TSharedPtr<SPygenesisChatWindow> Self = WeakSelf.Pin();
			if (!Self.IsValid())
			{
				return;
			}
			if (bOk)
			{
				Self->SetBusy(false);
				Self->SetStatus(FString::Printf(TEXT("Ya estaba en marcha — %s"), *Detail));
				Self->AppendTranscript(TEXT("Sistema"), TEXT("Backend ya activo; no se relanzo."));
				return;
			}

			Self->SetStatus(TEXT("Arrancando backend..."));
			const FPygenesisLaunchResult Launch = FPygenesisBackendLauncher::StartBackendDetached();
			Self->AppendTranscript(TEXT("Sistema"), Launch.Message);
			if (!Launch.bOk)
			{
				Self->SetBusy(false);
				Self->SetStatus(TEXT("No se pudo arrancar el backend"));
				FNotificationInfo Info(FText::FromString(Launch.Message));
				Info.ExpireDuration = 8.0f;
				FSlateNotificationManager::Get().AddNotification(Info);
				return;
			}

			// El modelo puede tardar ~30-90s en cargar
			Self->SetStatus(TEXT("Backend lanzado; esperando /health..."));
			Self->PollHealthAfterStart(45);
		}));

	return FReply::Handled();
}

void SPygenesisChatWindow::RememberAssistantReply(const FString& Reply)
{
	LastAssistantReply = Reply;
	if (Reply.Contains(TEXT("graph_name")) || Reply.Contains(TEXT("environment_type")))
	{
		LastStructuredReply = Reply;
		LastStructuredPrompt = LastUserPrompt;
	}
	// Habilitar Aplicar BP/Lighting en cuanto haya JSON (sin esperar a pulsar Health).
	Invalidate(EInvalidateWidgetReason::Layout | EInvalidateWidgetReason::Paint);
}

const FString& SPygenesisChatWindow::GetTextForApply() const
{
	return LastStructuredReply.IsEmpty() ? LastAssistantReply : LastStructuredReply;
}

FReply SPygenesisChatWindow::OnApplyBpLiteClicked()
{
	const FString& Source = GetTextForApply();
	if (Source.IsEmpty() || !Source.Contains(TEXT("graph_name")))
	{
		SetStatus(TEXT("No hay JSON BP-Lite para aplicar (genera un Blueprint primero)"));
		return FReply::Handled();
	}

	SetBusy(true);
	SetStatus(TEXT("Normalizando BP-Lite..."));

	TWeakPtr<SPygenesisChatWindow> WeakSelf = SharedThis(this);
	Client->PrepareBpLite(
		Source,
		LastStructuredPrompt.IsEmpty() ? LastUserPrompt : LastStructuredPrompt,
		FOnPygenesisBpLitePrepared::CreateLambda(
			[WeakSelf](bool bOk, const FString& GraphJson, const FString& Message)
			{
				TSharedPtr<SPygenesisChatWindow> Self = WeakSelf.Pin();
				if (!Self.IsValid())
				{
					return;
				}

				if (!bOk)
				{
					Self->SetBusy(false);
					Self->SetStatus(TEXT("BP-Lite: error"));
					Self->AppendTranscript(TEXT("Aplicar"), Message);
					return;
				}

				Self->SetStatus(TEXT("Creando Blueprint en /Game/Pygenesis..."));
				const FPygenesisBpApplyResult Apply = FPygenesisBpLiteApplier::ApplyFromJsonString(GraphJson);
				Self->SetBusy(false);
				Self->AppendTranscript(TEXT("Aplicar"), Apply.Message);
				Self->SetStatus(Apply.bOk ? TEXT("Blueprint creado") : TEXT("Fallo al crear Blueprint"));

				FNotificationInfo Info(FText::FromString(Apply.Message));
				Info.ExpireDuration = 6.0f;
				FSlateNotificationManager::Get().AddNotification(Info);
			}));

	return FReply::Handled();
}

FReply SPygenesisChatWindow::OnApplyLightingClicked()
{
	const FString& Source = GetTextForApply();
	if (Source.IsEmpty() || !Source.Contains(TEXT("environment_type")))
	{
		SetStatus(TEXT("No hay Lighting-Spec para aplicar (pide iluminacion primero)"));
		return FReply::Handled();
	}

	SetBusy(true);
	SetStatus(TEXT("Normalizando Lighting-Spec..."));

	TWeakPtr<SPygenesisChatWindow> WeakSelf = SharedThis(this);
	Client->PrepareLightingSpec(
		Source,
		FOnPygenesisLightingPrepared::CreateLambda(
			[WeakSelf](bool bOk, const FString& SpecJson, const FString& Message)
			{
				TSharedPtr<SPygenesisChatWindow> Self = WeakSelf.Pin();
				if (!Self.IsValid())
				{
					return;
				}

				if (!bOk)
				{
					Self->SetBusy(false);
					Self->SetStatus(TEXT("Lighting: error"));
					Self->AppendTranscript(TEXT("Aplicar Lighting"), Message);
					return;
				}

				Self->SetStatus(TEXT("Aplicando iluminacion al nivel..."));
				const FPygenesisLightingApplyResult Apply = FPygenesisLightingApplier::ApplyFromJsonString(SpecJson);
				Self->SetBusy(false);
				Self->AppendTranscript(TEXT("Aplicar Lighting"), Apply.Message);
				Self->SetStatus(Apply.bOk ? TEXT("Iluminacion aplicada") : TEXT("Fallo al aplicar iluminacion"));

				FNotificationInfo Info(FText::FromString(Apply.Message));
				Info.ExpireDuration = 6.0f;
				FSlateNotificationManager::Get().AddNotification(Info);
			}));

	return FReply::Handled();
}

FReply SPygenesisChatWindow::OnSendClicked()
{
	if (bBusy || !PromptBox.IsValid())
	{
		return FReply::Handled();
	}

	const FString Prompt = PromptBox->GetText().ToString().TrimStartAndEnd();
	if (Prompt.IsEmpty())
	{
		return FReply::Handled();
	}

	AppendTranscript(TEXT("Tu"), Prompt);
	bUserStopped = false;
	LastUserPrompt = Prompt;
	PromptBox->SetText(FText::GetEmpty());
	SetBusy(true);
	SetStatus(TEXT("Generando..."));
	BeginStreamingReply();

	TWeakPtr<SPygenesisChatWindow> WeakSelf = SharedThis(this);
	// Follow-up «sí» / explícame: el backend necesita el JSON+pregunta previos.
	// Tras una explicación en prosa, LastAssistantReply ya no trae graph_name → usar LastStructuredReply.
	FString PrevReply = LastAssistantReply;
	const bool bPrevHasStruct = PrevReply.Contains(TEXT("graph_name"))
		|| PrevReply.Contains(TEXT("environment_type"));
	if (!bPrevHasStruct && !LastStructuredReply.IsEmpty())
	{
		PrevReply = LastStructuredReply;
	}
	Client->Consultar(
		Prompt,
		TEXT("Contexto: chat general en Unreal Editor"),
		FOnPygenesisDone::CreateLambda(
			[WeakSelf](const FString& Reply, bool bOk)
			{
				TSharedPtr<SPygenesisChatWindow> Self = WeakSelf.Pin();
				if (!Self.IsValid())
				{
					return;
				}
				Self->SetBusy(false);
				Self->EndStreamingReply(Reply, bOk);
				// El status "Listo/Error" lo pone el typewriter al terminar el revelado
			}),
		FOnPygenesisPartial::CreateLambda(
			[WeakSelf](const FString& Partial)
			{
				TSharedPtr<SPygenesisChatWindow> Self = WeakSelf.Pin();
				if (Self.IsValid())
				{
					Self->UpdateStreamingReply(Partial);
				}
			}),
		PrevReply);

	return FReply::Handled();
}

FReply SPygenesisChatWindow::OnStopClicked()
{
	if (!bStreamingReply || !Client.IsValid())
	{
		return FReply::Handled();
	}
	bUserStopped = true;
	SetStatus(TEXT("Deteniendo..."));
	Client->CancelActiveJob();
	return FReply::Handled();
}

FReply SPygenesisChatWindow::OnClearChatClicked()
{
	if (bBusy)
	{
		return FReply::Handled();
	}
	LastAssistantReply.Reset();
	LastStructuredReply.Reset();
	LastStructuredPrompt.Reset();
	LastUserPrompt.Reset();
	bUserStopped = false;
	bStreamingReply = false;
	bFinalizePending = false;
	StreamTargetText.Reset();
	StreamVisibleChars = 0;
	TranscriptBeforeStream.Reset();
	if (TranscriptBox.IsValid())
	{
		TranscriptBox->SetText(LOCTEXT(
			"Welcome",
			"Pygenesis Unreal — asistente local.\n"
			"1) Iniciar Backend (si hace falta) → Health\n"
			"2) Pide un Blueprint o una atmosfera/iluminacion\n"
			"3) Aplicar BP-Lite o Aplicar Lighting segun el JSON\n"
			"Detener corta la generacion y deja lo ya escrito. Limpiar vacia el chat.\n"));
	}
	SetStatus(TEXT("Chat limpio"));
	Invalidate(EInvalidateWidgetReason::Layout | EInvalidateWidgetReason::Paint);
	return FReply::Handled();
}

#undef LOCTEXT_NAMESPACE
