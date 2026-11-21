#pragma once

#include "CoreMinimal.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "TimerManager.h"

DECLARE_DELEGATE_TwoParams(FOnPygenesisDone, const FString& /*FullReply*/, bool /*bOk*/);
DECLARE_DELEGATE_OneParam(FOnPygenesisPartial, const FString& /*PartialReply*/);
DECLARE_DELEGATE_TwoParams(FOnPygenesisHealth, bool /*bOk*/, const FString& /*Detail*/);
DECLARE_DELEGATE_ThreeParams(FOnPygenesisBpLitePrepared, bool /*bOk*/, const FString& /*GraphJson*/, const FString& /*Message*/);
DECLARE_DELEGATE_ThreeParams(FOnPygenesisLightingPrepared, bool /*bOk*/, const FString& /*SpecJson*/, const FString& /*Message*/);

/**
 * Cliente HTTP hacia el puente FastAPI.
 * Consultas: POST /consultar/async + polling (con texto parcial mientras genera).
 * BP-Lite: POST /aplicar/bp-lite.
 * Lighting: POST /aplicar/lighting-spec.
 */
class FPygenesisBridgeClient : public TSharedFromThis<FPygenesisBridgeClient>
{
public:
	explicit FPygenesisBridgeClient(const FString& InBaseUrl = TEXT("http://127.0.0.1:8000"));
	~FPygenesisBridgeClient();

	void CheckHealth(FOnPygenesisHealth OnComplete);
	void Consultar(
		const FString& Prompt,
		const FString& ContextoProyecto,
		FOnPygenesisDone OnComplete,
		FOnPygenesisPartial OnPartial = FOnPygenesisPartial(),
		const FString& UltimaRespuesta = FString());
	void PrepareBpLite(
		const FString& AssistantText,
		const FString& UserPrompt,
		FOnPygenesisBpLitePrepared OnComplete);
	void PrepareLightingSpec(const FString& AssistantText, FOnPygenesisLightingPrepared OnComplete);
	/** Corta el job en curso. El poll sigue hasta que el backend deja lo ya escrito. */
	void CancelActiveJob();

	const FString& GetBaseUrl() const { return BaseUrl; }

private:
	FString BaseUrl;
	TSharedPtr<IHttpRequest, ESPMode::ThreadSafe> ActiveRequest;
	FOnPygenesisDone PendingDone;
	FOnPygenesisPartial PendingPartial;
	FString ActiveJobId;
	FString LastPartialSeen;
	bool bCancelRequested = false;
	TSharedPtr<IHttpRequest, ESPMode::ThreadSafe> CancelRequest;
	FString PendingUltimaRespuesta;
	int32 StalePartialPolls = 0;
	FTimerHandle PollTimer;
	int32 PollAttempts = 0;
	static constexpr int32 MaxPollAttempts = 2400; // ~4 min a 0.1s

	void StartJob(const FString& Prompt, const FString& ContextoProyecto);
	void SendCancel(const FString& JobId);
	void PollJobOnce();
	void Finish(bool bOk, const FString& Message);
	void ClearPollTimer();
};
