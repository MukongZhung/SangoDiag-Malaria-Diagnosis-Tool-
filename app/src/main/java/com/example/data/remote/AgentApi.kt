package com.example.data.remote

import com.squareup.moshi.Json
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import java.util.concurrent.TimeUnit

// Mirrors the Python API in agent/api.py

data class DiagnoseRequest(
    @Json(name = "patient_id") val patientId: String,
    val symptoms: String,
    @Json(name = "image_result") val imageResult: String,
    @Json(name = "weight_kg") val weightKg: Double? = null
)

data class AssessmentDto(
    val diagnosis: String,
    val treatment: String,
    @Json(name = "test_result") val testResult: String,
    val temperature: Double?,
    @Json(name = "severe_signs") val severeSigns: List<String> = emptyList(),
    @Json(name = "is_severe") val isSevere: Boolean,
    val village: String?,
    @Json(name = "endemic_zone") val endemicZone: String?,
    @Json(name = "active_cases") val activeCases: String?,
    @Json(name = "coartem_tablets_per_dose") val coartemTabletsPerDose: Int?
)

data class LlmCallDto(
    val mode: String,
    @Json(name = "executed_model") val executedModel: String?,
    @Json(name = "routing_lane") val routingLane: String?,
    @Json(name = "latency_ms") val latencyMs: Long
)

data class DiagnoseResponse(
    @Json(name = "patient_id") val patientId: String,
    val report: String,
    @Json(name = "safety_alert") val safetyAlert: String?,
    val assessment: AssessmentDto,
    @Json(name = "sql_queries") val sqlQueries: List<String> = emptyList(),
    @Json(name = "sql_rows") val sqlRows: List<Map<String, Any?>> = emptyList(),
    @Json(name = "memory_before") val memoryBefore: String?,
    @Json(name = "memory_saved_note") val memorySavedNote: String,
    @Json(name = "llm_calls") val llmCalls: List<LlmCallDto> = emptyList()
)

data class HealthResponse(
    val status: String,
    val nightshift: String,
    val zetaris: String,
    val model: String
)

interface AgentApi {
    @GET("health")
    suspend fun health(): HealthResponse

    @POST("diagnose")
    suspend fun diagnose(@Body request: DiagnoseRequest): DiagnoseResponse

    companion object {
        fun create(baseUrl: String): AgentApi {
            val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
            val client = OkHttpClient.Builder()
                .connectTimeout(5, TimeUnit.SECONDS)
                // Nightshift turns can take a while on a slow uplink
                .readTimeout(120, TimeUnit.SECONDS)
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
