package com.example.data.models

data class Patient(
    val patientId: String,
    val name: String,
    val village: String,
    val familyHistory: Boolean,
    val age: Int,
    val gender: String,
    val phone: String = "+237 6XX-XX-XX-XX"
)

data class ClinicalVisit(
    val visitId: String,
    val patientId: String,
    val feverTemp: Float,
    val bodyPain: Boolean,
    val date: String = "2026-10-24"
)

data class EpidemiologyZone(
    val village: String,
    val region: String,
    val endemicZone: String, // "High", "Medium", "Low"
    val activeCases: Int,
    val vectorRisk: String = "Anopheles gambiae high density"
)

data class SymptomsState(
    val feverTemp: Float = 39.4f,
    val headache: Boolean = true,
    val bodyPain: Boolean = true,
    val chills: Boolean = true,
    val vomiting: Boolean = true,
    val durationDays: Int = 2
)

data class RdtStatus(
    val isPositive: Boolean = true,
    val hasControlLine: Boolean = true,
    val antigen: String = "HRP-2 (Plasmodium falciparum)"
)

data class MicroscopyStatus(
    val parasitesPerMicroLiter: Int = 18500,
    val species: String = "P. falciparum ring-form trophozoites",
    val trophozoitesObserved: Boolean = true
)

enum class StepStatus {
    PENDING,
    RUNNING,
    SUCCESS,
    FAILED
}

data class AgentExecutionStep(
    val stepIndex: Int,
    val tag: String,
    val title: String,
    val status: StepStatus,
    val subtitle: String,
    val details: String = ""
)

data class NightshiftAudit(
    val targetModel: String,
    val executedModel: String,
    val routingLane: String,
    val latencyMs: Long,
    val tokensPerSec: Int,
    val appHeader: String = "meterless-app: malaria-agent",
    val scopeHeader: String = "meterless-scope: user"
)

data class DiagnosisResult(
    val patientId: String,
    val clinicalSummary: String,
    val prescriptionAct: String,
    val supportiveCare: String,
    val dangerSigns: List<String>,
    val sqlQuery: String,
    val sqlRowsReturned: Int,
    val hMemBefore: String?,
    val hMemSavedNote: String,
    val audit: NightshiftAudit
)
