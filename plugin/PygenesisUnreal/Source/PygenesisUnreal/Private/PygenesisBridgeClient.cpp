#include "PygenesisBridgeClient.h"

#include "HttpModule.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Editor.h"
#include "Engine/World.h"

DEFINE_LOG_CATEGORY_STATIC(LogPygenesisBridge, Log, All);

FPygenesisBridgeClient::FPygenesisBridgeClient(const FString& InBaseUrl)
	: BaseUrl(InBaseUrl.IsEmpty() ? TEXT("http://127.0.0.1:8000") : InBaseUrl)
{
	while (BaseUrl.EndsWith(TEXT("/")))
	{
		BaseUrl.LeftChopInline(1);
	}
}

FPygenesisBridgeClient::~FPygenesisBridgeClient()
{
	ClearPollTimer();
}

void FPygenesisBridgeClient::ClearPollTimer()
{
	if (GEditor)
	{
		if (UWorld* World = GEditor->GetEditorWorldContext().World())
		{
			World->GetTimerManager().ClearTimer(PollTimer);
		}
	}
}

void FPygenesisBridgeClient::Finish(bool bOk, const FString& Message)
{
	ClearPollTimer();
	ActiveRequest.Reset();
	ActiveJobId.Reset();
	LastPartialSeen.Reset();
	PollAttempts = 0;
	FOnPygenesisDone Done = PendingDone;
	PendingDone.Unbind();
	PendingPartial.Unbind();
	Done.ExecuteIfBound(Message, bOk);
}

void FPygenesisBridgeClient::CheckHealth(FOnPygenesisHealth OnComplete)
{
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
	ActiveRequest = Request;
	Request->SetURL(BaseUrl + TEXT("/health"));
	Request->SetVerb(TEXT("GET"));
	Request->SetTimeout(10.0f);

	TWeakPtr<FPygenesisBridgeClient> WeakSelf = AsShared();
	Request->OnProcessRequestComplete().BindLambda(
		[WeakSelf, OnComplete](FHttpRequestPtr /*Req*/, FHttpResponsePtr Response, bool bConnected)
		{
			if (TSharedPtr<FPygenesisBridgeClient> Self = WeakSelf.Pin())
			{
				Self->ActiveRequest.Reset();
			}
			if (!bConnected || !Response.IsValid())
			{
				OnComplete.ExecuteIfBound(false, TEXT("No hay conexion con el puente (¿backend arrancado?)"));
				return;
			}
			const int32 Code = Response->GetResponseCode();
			if (Code < 200 || Code >= 300)
			{
				OnComplete.ExecuteIfBound(false, FString::Printf(TEXT("HTTP %d"), Code));
				return;
			}

			TSharedPtr<FJsonObject> Json;
			const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Response->GetContentAsString());
			if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
			{
				OnComplete.ExecuteIfBound(false, TEXT("Respuesta /health invalida"));
				return;
			}

			FString Status = TEXT("unknown");
			Json->TryGetStringField(TEXT("status"), Status);
			bool bLoaded = false;
			Json->TryGetBoolField(TEXT("model_loaded"), bLoaded);
			FString Backend = TEXT("?");
			Json->TryGetStringField(TEXT("backend"), Backend);
			const FString Detail = FString::Printf(
				TEXT("%s | backend=%s | model_loaded=%s"),
				*Status,
				*Backend,
				bLoaded ? TEXT("true") : TEXT("false"));
			OnComplete.ExecuteIfBound(true, Detail);
		});
	Request->ProcessRequest();
}

void FPygenesisBridgeClient::Consultar(
	const FString& Prompt,
	const FString& ContextoProyecto,
	FOnPygenesisDone OnComplete,
	FOnPygenesisPartial OnPartial,
	const FString& UltimaRespuesta)
{
	ClearPollTimer();
	PendingDone = OnComplete;
	PendingPartial = OnPartial;
	PendingUltimaRespuesta = UltimaRespuesta;
	PollAttempts = 0;
	bCancelRequested = false;
	ActiveJobId.Reset();
	LastPartialSeen.Reset();
	StalePartialPolls = 0;
	StartJob(Prompt, ContextoProyecto);
}

void FPygenesisBridgeClient::StartJob(
	const FString& Prompt,
	const FString& ContextoProyecto)
{
	TSharedPtr<FJsonObject> Body = MakeShared<FJsonObject>();
	Body->SetStringField(TEXT("prompt"), Prompt);
	Body->SetStringField(TEXT("contexto_proyecto"), ContextoProyecto);
	Body->SetBoolField(TEXT("modo_json"), false);
	if (!PendingUltimaRespuesta.IsEmpty())
	{
		// Limitar tamaño del body HTTP
		Body->SetStringField(TEXT("ultima_respuesta"), PendingUltimaRespuesta.Left(3500));
	}

	FString BodyStr;
	const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&BodyStr);
	FJsonSerializer::Serialize(Body.ToSharedRef(), Writer);

	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
	ActiveRequest = Request;
	Request->SetURL(BaseUrl + TEXT("/consultar/async"));
	Request->SetVerb(TEXT("POST"));
	Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
	Request->SetContentAsString(BodyStr);
	Request->SetTimeout(30.0f);

	UE_LOG(LogPygenesisBridge, Display, TEXT("POST %s/consultar/async"), *BaseUrl);

	TWeakPtr<FPygenesisBridgeClient> WeakSelf = AsShared();
	Request->OnProcessRequestComplete().BindLambda(
		[WeakSelf](FHttpRequestPtr /*Req*/, FHttpResponsePtr Response, bool bConnected)
		{
			TSharedPtr<FPygenesisBridgeClient> Self = WeakSelf.Pin();
			if (!Self.IsValid())
			{
				return;
			}
			Self->ActiveRequest.Reset();

			if (!bConnected || !Response.IsValid())
			{
				Self->Finish(false, TEXT("Error: no se pudo crear el job async. ¿Backend en 127.0.0.1:8000?"));
				return;
			}
			const int32 Code = Response->GetResponseCode();
			const FString Content = Response->GetContentAsString();
			if (Code < 200 || Code >= 300)
			{
				Self->Finish(false, FString::Printf(TEXT("Error HTTP %d al crear job: %s"), Code, *Content.Left(300)));
				return;
			}

			TSharedPtr<FJsonObject> Json;
			const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Content);
			FString JobId;
			if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid() || !Json->TryGetStringField(TEXT("job_id"), JobId))
			{
				Self->Finish(false, TEXT("Error: respuesta /consultar/async sin job_id"));
				return;
			}

			Self->ActiveJobId = JobId;
			UE_LOG(LogPygenesisBridge, Display, TEXT("Job encolado: %s"), *JobId);
			if (Self->bCancelRequested)
			{
				Self->SendCancel(JobId);
			}

			if (!GEditor)
			{
				Self->Finish(false, TEXT("Error: GEditor no disponible para polling"));
				return;
			}
			UWorld* World = GEditor->GetEditorWorldContext().World();
			if (!World)
			{
				Self->Finish(false, TEXT("Error: no hay World del editor para timers"));
				return;
			}

			// Poll ~10 Hz para stream más fluido
			World->GetTimerManager().SetTimer(
				Self->PollTimer,
				FTimerDelegate::CreateLambda([WeakSelf]()
				{
					if (TSharedPtr<FPygenesisBridgeClient> S = WeakSelf.Pin())
					{
						S->PollJobOnce();
					}
				}),
				0.1f,
				true);
		});

	if (!Request->ProcessRequest())
	{
		ActiveRequest.Reset();
		Finish(false, TEXT("Error: ProcessRequest() rechazo /consultar/async"));
	}
}

void FPygenesisBridgeClient::CancelActiveJob()
{
	bCancelRequested = true;
	if (!ActiveJobId.IsEmpty())
	{
		SendCancel(ActiveJobId);
	}
}

void FPygenesisBridgeClient::SendCancel(const FString& JobId)
{
	if (JobId.IsEmpty())
	{
		return;
	}
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
	CancelRequest = Request;
	Request->SetURL(BaseUrl + TEXT("/consultar/job/") + JobId + TEXT("/cancel"));
	Request->SetVerb(TEXT("POST"));
	Request->SetTimeout(10.0f);
	UE_LOG(LogPygenesisBridge, Display, TEXT("POST cancel job %s"), *JobId);

	TWeakPtr<FPygenesisBridgeClient> WeakSelf = AsShared();
	Request->OnProcessRequestComplete().BindLambda(
		[WeakSelf](FHttpRequestPtr /*Req*/, FHttpResponsePtr Response, bool bConnected)
		{
			if (TSharedPtr<FPygenesisBridgeClient> Self = WeakSelf.Pin())
			{
				Self->CancelRequest.Reset();
			}
			if (!bConnected || !Response.IsValid() || Response->GetResponseCode() >= 300)
			{
				UE_LOG(LogPygenesisBridge, Warning, TEXT("Cancel del job no confirmado"));
			}
		});
	Request->ProcessRequest();
}

void FPygenesisBridgeClient::PollJobOnce()
{
	if (ActiveJobId.IsEmpty())
	{
		ClearPollTimer();
		return;
	}
	// Evitar solapar polls HTTP
	if (ActiveRequest.IsValid())
	{
		return;
	}

	++PollAttempts;
	if (PollAttempts > MaxPollAttempts)
	{
		// Si ya llegó texto útil (p.ej. JSON + explicación) y el modelo se quedó en bucle,
		// devolvemos lo acumulado en vez de error vacío.
		if (!LastPartialSeen.IsEmpty() && LastPartialSeen.Len() > 20)
		{
			Finish(true, LastPartialSeen);
		}
		else
		{
			Finish(false, TEXT("Timeout esperando el job (~6 min). Reinicia el backend o reduce la pregunta."));
		}
		return;
	}

	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
	ActiveRequest = Request;
	Request->SetURL(BaseUrl + TEXT("/consultar/job/") + ActiveJobId);
	Request->SetVerb(TEXT("GET"));
	Request->SetTimeout(10.0f);

	TWeakPtr<FPygenesisBridgeClient> WeakSelf = AsShared();
	Request->OnProcessRequestComplete().BindLambda(
		[WeakSelf](FHttpRequestPtr /*Req*/, FHttpResponsePtr Response, bool bConnected)
		{
			TSharedPtr<FPygenesisBridgeClient> Self = WeakSelf.Pin();
			if (!Self.IsValid())
			{
				return;
			}
			Self->ActiveRequest.Reset();

			if (!bConnected || !Response.IsValid())
			{
				UE_LOG(LogPygenesisBridge, Warning, TEXT("Poll fallido (intento %d), reintento..."), Self->PollAttempts);
				return;
			}

			const int32 Code = Response->GetResponseCode();
			const FString Content = Response->GetContentAsString();
			if (Code == 404)
			{
				Self->Finish(false, TEXT("Error: job perdido en el backend (reinicio?)"));
				return;
			}
			if (Code < 200 || Code >= 300)
			{
				Self->Finish(false, FString::Printf(TEXT("Error HTTP %d en poll: %s"), Code, *Content.Left(300)));
				return;
			}

			TSharedPtr<FJsonObject> Json;
			const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Content);
			if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
			{
				return;
			}

			FString Status;
			Json->TryGetStringField(TEXT("status"), Status);

			FString Phase;
			Json->TryGetStringField(TEXT("phase"), Phase);

			FString Partial;
			Json->TryGetStringField(TEXT("respuesta"), Partial);
			if (!Partial.IsEmpty() && Partial != Self->LastPartialSeen)
			{
				Self->LastPartialSeen = Partial;
				Self->StalePartialPolls = 0;
				Self->PendingPartial.ExecuteIfBound(Partial);
			}
			else if (!Partial.IsEmpty())
			{
				++Self->StalePartialPolls;
			}

			if (Status.Equals(TEXT("running"), ESearchCase::IgnoreCase))
			{
				if (Partial.IsEmpty() && Phase.Equals(TEXT("preparando"), ESearchCase::IgnoreCase))
				{
					// Prefilling: sin tokens todavía
				}
				// Rescate si el backend se queda colgado tras un JSON ya cerrado (~12 s).
				// «completando» / «reintentando» es el segundo pase: el primer
				// BeginPlay ya está cerrado y no hay que dar el job por terminado.
				const bool bSecondPass = Phase.Equals(TEXT("completando"), ESearchCase::IgnoreCase)
					|| Phase.Equals(TEXT("reintentando"), ESearchCase::IgnoreCase);
				const bool bLooksComplete = !bSecondPass
					&& (Partial.Contains(TEXT("graph_name")) || Partial.Contains(TEXT("environment_type")))
					&& Partial.Contains(TEXT("```"))
					&& Self->StalePartialPolls >= 120;
				if (bLooksComplete && Partial.Len() > 80)
				{
					Self->Finish(true, Partial);
				}
				return;
			}
			if (Status.Equals(TEXT("error"), ESearchCase::IgnoreCase))
			{
				FString Err;
				Json->TryGetStringField(TEXT("error"), Err);
				Self->Finish(false, FString::Printf(TEXT("Error del modelo: %s"), *Err));
				return;
			}
			if (Status.Equals(TEXT("done"), ESearchCase::IgnoreCase))
			{
				FString Reply = Partial;
				if (Reply.IsEmpty())
				{
					Json->TryGetStringField(TEXT("respuesta"), Reply);
				}
				// El done del backend es el JSON ya normalizado (ejes A/D, sin Branch).
				// No volver al parcial del stream solo porque es más largo: ese es el
				// JSON crudo del modelo, con WorldDirection [-1,0,0].
				const bool bDoneHasGraph = Reply.Contains(TEXT("graph_name"))
					|| Reply.Contains(TEXT("environment_type"));
				if (!bDoneHasGraph && (Reply.IsEmpty()
					|| (!Self->LastPartialSeen.IsEmpty() && Reply.Len() + 32 < Self->LastPartialSeen.Len())))
				{
					Reply = Self->LastPartialSeen;
				}
				Self->Finish(true, Reply.IsEmpty() ? TEXT("(vacio)") : Reply);
			}
		});

	Request->ProcessRequest();
}

void FPygenesisBridgeClient::PrepareBpLite(
	const FString& AssistantText,
	const FString& UserPrompt,
	FOnPygenesisBpLitePrepared OnComplete)
{
	TSharedPtr<FJsonObject> Body = MakeShared<FJsonObject>();
	Body->SetStringField(TEXT("texto"), AssistantText);
	Body->SetStringField(TEXT("asset_path"), TEXT("/Game/Pygenesis"));
	// Sin la peticion original el backend no sabe si un PrintString suelto era pedido
	Body->SetStringField(TEXT("prompt"), UserPrompt);

	FString BodyStr;
	const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&BodyStr);
	FJsonSerializer::Serialize(Body.ToSharedRef(), Writer);

	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
	ActiveRequest = Request;
	Request->SetURL(BaseUrl + TEXT("/aplicar/bp-lite"));
	Request->SetVerb(TEXT("POST"));
	Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
	Request->SetContentAsString(BodyStr);
	Request->SetTimeout(30.0f);

	TWeakPtr<FPygenesisBridgeClient> WeakSelf = AsShared();
	Request->OnProcessRequestComplete().BindLambda(
		[WeakSelf, OnComplete](FHttpRequestPtr /*Req*/, FHttpResponsePtr Response, bool bConnected)
		{
			if (TSharedPtr<FPygenesisBridgeClient> Self = WeakSelf.Pin())
			{
				Self->ActiveRequest.Reset();
			}
			if (!bConnected || !Response.IsValid())
			{
				OnComplete.ExecuteIfBound(false, TEXT(""), TEXT("No se pudo contactar /aplicar/bp-lite"));
				return;
			}
			const int32 Code = Response->GetResponseCode();
			const FString Content = Response->GetContentAsString();
			if (Code < 200 || Code >= 300)
			{
				OnComplete.ExecuteIfBound(false, TEXT(""), FString::Printf(TEXT("HTTP %d: %s"), Code, *Content.Left(400)));
				return;
			}

			TSharedPtr<FJsonObject> Json;
			const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Content);
			if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
			{
				OnComplete.ExecuteIfBound(false, TEXT(""), TEXT("Respuesta /aplicar/bp-lite invalida"));
				return;
			}

			const TSharedPtr<FJsonObject>* GraphObj = nullptr;
			if (!Json->TryGetObjectField(TEXT("graph"), GraphObj) || GraphObj == nullptr || !GraphObj->IsValid())
			{
				OnComplete.ExecuteIfBound(false, TEXT(""), TEXT("Respuesta sin graph"));
				return;
			}

			FString GraphJson;
			const TSharedRef<TJsonWriter<>> GraphWriter = TJsonWriterFactory<>::Create(&GraphJson);
			FJsonSerializer::Serialize(GraphObj->ToSharedRef(), GraphWriter);

			FString Summary;
			Json->TryGetStringField(TEXT("summary"), Summary);
			OnComplete.ExecuteIfBound(true, GraphJson, Summary.IsEmpty() ? TEXT("BP-Lite listo") : Summary);
		});

	if (!Request->ProcessRequest())
	{
		ActiveRequest.Reset();
		OnComplete.ExecuteIfBound(false, TEXT(""), TEXT("ProcessRequest rechazo /aplicar/bp-lite"));
	}
}

void FPygenesisBridgeClient::PrepareLightingSpec(const FString& AssistantText, FOnPygenesisLightingPrepared OnComplete)
{
	TSharedPtr<FJsonObject> Body = MakeShared<FJsonObject>();
	Body->SetStringField(TEXT("texto"), AssistantText);

	FString BodyStr;
	const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&BodyStr);
	FJsonSerializer::Serialize(Body.ToSharedRef(), Writer);

	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
	ActiveRequest = Request;
	Request->SetURL(BaseUrl + TEXT("/aplicar/lighting-spec"));
	Request->SetVerb(TEXT("POST"));
	Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
	Request->SetContentAsString(BodyStr);
	Request->SetTimeout(30.0f);

	TWeakPtr<FPygenesisBridgeClient> WeakSelf = AsShared();
	Request->OnProcessRequestComplete().BindLambda(
		[WeakSelf, OnComplete](FHttpRequestPtr /*Req*/, FHttpResponsePtr Response, bool bConnected)
		{
			if (TSharedPtr<FPygenesisBridgeClient> Self = WeakSelf.Pin())
			{
				Self->ActiveRequest.Reset();
			}
			if (!bConnected || !Response.IsValid())
			{
				OnComplete.ExecuteIfBound(false, TEXT(""), TEXT("No se pudo contactar /aplicar/lighting-spec"));
				return;
			}
			const int32 Code = Response->GetResponseCode();
			const FString Content = Response->GetContentAsString();
			if (Code < 200 || Code >= 300)
			{
				OnComplete.ExecuteIfBound(false, TEXT(""), FString::Printf(TEXT("HTTP %d: %s"), Code, *Content.Left(400)));
				return;
			}

			TSharedPtr<FJsonObject> Json;
			const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Content);
			if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
			{
				OnComplete.ExecuteIfBound(false, TEXT(""), TEXT("Respuesta /aplicar/lighting-spec invalida"));
				return;
			}

			const TSharedPtr<FJsonObject>* SpecObj = nullptr;
			if (!Json->TryGetObjectField(TEXT("spec"), SpecObj) || SpecObj == nullptr || !SpecObj->IsValid())
			{
				OnComplete.ExecuteIfBound(false, TEXT(""), TEXT("Respuesta sin spec"));
				return;
			}

			FString SpecJson;
			const TSharedRef<TJsonWriter<>> SpecWriter = TJsonWriterFactory<>::Create(&SpecJson);
			FJsonSerializer::Serialize(SpecObj->ToSharedRef(), SpecWriter);

			FString Summary;
			Json->TryGetStringField(TEXT("summary"), Summary);
			OnComplete.ExecuteIfBound(true, SpecJson, Summary.IsEmpty() ? TEXT("Lighting-Spec listo") : Summary);
		});

	if (!Request->ProcessRequest())
	{
		ActiveRequest.Reset();
		OnComplete.ExecuteIfBound(false, TEXT(""), TEXT("ProcessRequest rechazo /aplicar/lighting-spec"));
	}
}
