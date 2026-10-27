package com.example.data.remote

import com.squareup.moshi.Json
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.Body
import retrofit2.http.POST
import java.util.concurrent.TimeUnit

// Mirrors agent/api.py, which runs agent.agent.run_case (same agent as the Streamlit UI)

data class DiagnoseRequest(
    @Json(name = "patient_id") val patientId: String,
    @Json(name = "temperature_c") val temperatureC: Double? = null,
    @Json(name = "fever_days") val feverDays: Int? = null,
    @Json(name = "age_years") val ageYears: Double? = null,
    val symptoms: List<String> = emptyList(),
    @Json(name = "danger_signs") val dangerSigns: List<String> = emptyList(),
    @Json(name = "recent_travel") val recentTravel: Boolean = false,
    @Json(name = "household_cases") val householdCases: Boolean = false,
    @Json(name = "test_result") val testResult: String = "not_done"
)

data class TriageDto(
    val score: Int,
    val level: String,
    val action: String,
    @Json(name = "action_label") val actionLabel: String,
    val urgent: Boolean,
    val confidence: String,
    val abstain: Boolean,
    @Json(name = "next_steps") val nextSteps: List<String> = emptyList(),
    val missing: List<String> = emptyList()
)

data class QueryDto(
    val qid: String?,
    val sql: String,
    val source: String,
    val rows: List<Map<String, Any?>> = emptyList(),
    val error: String?,
    @Json(name = "asked_by") val askedBy: String?
)

data class CallDto(
    val lane: String,
    val role: String,
    @Json(name = "model_reported") val modelReported: String,
    val live: Boolean,
    @Json(name = "latency_ms") val latencyMs: Long
)

data class MemoryItemDto(
    val content: String,
    @Json(name = "when") val `when`: String?
)

data class MemoryDto(
    val count: Int = 0,
    val items: List<MemoryItemDto> = emptyList()
)

data class RunResultDto(
    @Json(name = "run_id") val runId: String,
    val triage: TriageDto?,
    val report: String = "",
    @Json(name = "report_source") val reportSource: String = "",
    val queries: List<QueryDto> = emptyList(),
    val calls: List<CallDto> = emptyList(),
    val memory: MemoryDto = MemoryDto(),
    @Json(name = "memory_written") val memoryWritten: List<String> = emptyList(),
    val error: String?,
    @Json(name = "elapsed_s") val elapsedS: Double = 0.0
)

interface AgentApi {
    @POST("diagnose")
    suspend fun diagnose(@Body request: DiagnoseRequest): RunResultDto

    companion object {
        fun create(baseUrl: String): AgentApi {
            val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
            val client = OkHttpClient.Builder()
                .connectTimeout(5, TimeUnit.SECONDS)
                // Planner + reporter turns on Nightshift can take minutes (meterless-ttfb-ms is 240 s)
                .readTimeout(300, TimeUnit.SECONDS)
                .build()
            return Retrofit.Builder()
                .baseUrl(if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/")
                .client(client)
                .addConverterFactory(MoshiConverterFactory.create(moshi))
                .build()
                .create(AgentApi::class.java)
        }
    }
}
