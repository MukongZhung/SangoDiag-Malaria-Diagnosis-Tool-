package com.example.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.data.SyntheticDataProvider
import com.example.data.local.AppDatabase
import com.example.data.local.HMemEntity
import com.example.data.models.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.*

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val db = AppDatabase.getDatabase(application)
    private val hMemDao = db.hMemDao()

    // Patients & Selected Patient
    val patients = SyntheticDataProvider.patients
    private val _selectedPatient = MutableStateFlow(patients.first())
    val selectedPatient: StateFlow<Patient> = _selectedPatient.asStateFlow()

    // Symptoms State
    private val _symptoms = MutableStateFlow(SymptomsState())
    val symptoms: StateFlow<SymptomsState> = _symptoms.asStateFlow()

    // Diagnostic Test State
    private val _rdtStatus = MutableStateFlow(RdtStatus())
    val rdtStatus: StateFlow<RdtStatus> = _rdtStatus.asStateFlow()

    private val _microscopyStatus = MutableStateFlow(MicroscopyStatus())
    val microscopyStatus: StateFlow<MicroscopyStatus> = _microscopyStatus.asStateFlow()

    // Agent Execution Flow State
    private val _isAgentRunning = MutableStateFlow(false)
    val isAgentRunning: StateFlow<Boolean> = _isAgentRunning.asStateFlow()

    private val _executionSteps = MutableStateFlow<List<AgentExecutionStep>>(emptyList())
    val executionSteps: StateFlow<List<AgentExecutionStep>> = _executionSteps.asStateFlow()

    private val _finalDiagnosis = MutableStateFlow<DiagnosisResult?>(null)
    val finalDiagnosis: StateFlow<DiagnosisResult?> = _finalDiagnosis.asStateFlow()

    // H-MEM Room Persistence Stream
    val allMemories: StateFlow<List<HMemEntity>> = hMemDao.getAllPatientMemories()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    // Zetaris SQL Query Studio State
    private val _currentSql = MutableStateFlow("SELECT p.patient_id, p.village, p.family_history, e.endemic_zone, e.active_cases FROM patients p JOIN regional_epidemiology e ON p.village = e.village WHERE e.endemic_zone = 'High';")
    val currentSql: StateFlow<String> = _currentSql.asStateFlow()

    private val _sqlResults = MutableStateFlow<List<Map<String, String>>>(emptyList())
    val sqlResults: StateFlow<List<Map<String, String>>> = _sqlResults.asStateFlow()

    private val _sqlExecutionTimeMs = MutableStateFlow(0L)
    val sqlExecutionTimeMs: StateFlow<Long> = _sqlExecutionTimeMs.asStateFlow()

    private val _sqlRequestId = MutableStateFlow(UUID.randomUUID().toString())
    val sqlRequestId: StateFlow<String> = _sqlRequestId.asStateFlow()

    // Settings
    private val _meterlessBaseUrl = MutableStateFlow("https://runtime.meterless.ai/v1")
    val meterlessBaseUrl: StateFlow<String> = _meterlessBaseUrl.asStateFlow()

    private val _meterlessToken = MutableStateFlow("demo_token_nightshift")
    val meterlessToken: StateFlow<String> = _meterlessToken.asStateFlow()

    private val _meterlessModel = MutableStateFlow("nvidia/nemotron-3.5-lightning-30b-a3b")
    val meterlessModel: StateFlow<String> = _meterlessModel.asStateFlow()

    private val _zetarisBaseUrl = MutableStateFlow("http://localhost:8888/api/v1.0")
    val zetarisBaseUrl: StateFlow<String> = _zetarisBaseUrl.asStateFlow()

    private val _zetarisApiKey = MutableStateFlow("demo_zetaris_key")
    val zetarisApiKey: StateFlow<String> = _zetarisApiKey.asStateFlow()

    private val _autonomousFieldMode = MutableStateFlow(true)
    val autonomousFieldMode: StateFlow<Boolean> = _autonomousFieldMode.asStateFlow()

    init {
        // Pre-populate sample H-MEM records if empty
        viewModelScope.launch {
            val existing = hMemDao.getPatientMemory("123")
            if (existing == null) {
                hMemDao.savePatientMemory(
                    HMemEntity(
                        patientId = "123",
                        contextString = "[2026-08-15 Previous Visit]: Treated for uncomplicated malaria in Buea. Fully resolved on Coartem. No reported adverse reactions.",
                        updatedAt = "2026-08-15 10:20:00",
                        sessionCount = 1
                    )
                )
                hMemDao.savePatientMemory(
                    HMemEntity(
                        patientId = "p101-buea-482a-991f",
                        contextString = "[2026-09-02 Initial Intake]: Patient confirmed G6PD normal. History of recurrent febrile illness during rainy season.",
                        updatedAt = "2026-09-02 14:15:00",
                        sessionCount = 1
                    )
                )
            }
            // Execute default SQL
            runSqlQuery(_currentSql.value)
        }
    }

    fun selectPatient(patient: Patient) {
        _selectedPatient.value = patient
        _finalDiagnosis.value = null
        _executionSteps.value = emptyList()
    }

    fun updateFeverTemp(temp: Float) {
        _symptoms.value = _symptoms.value.copy(feverTemp = temp)
    }

    fun toggleSymptom(headache: Boolean? = null, bodyPain: Boolean? = null, chills: Boolean? = null, vomiting: Boolean? = null) {
        val curr = _symptoms.value
        _symptoms.value = curr.copy(
            headache = headache ?: curr.headache,
            bodyPain = bodyPain ?: curr.bodyPain,
            chills = chills ?: curr.chills,
            vomiting = vomiting ?: curr.vomiting
        )
    }

    fun toggleRdtResult(positive: Boolean) {
        _rdtStatus.value = _rdtStatus.value.copy(isPositive = positive)
    }

    fun setSqlQuery(query: String) {
        _currentSql.value = query
    }

    fun runSqlQuery(query: String) {
        viewModelScope.launch {
            val startTime = System.currentTimeMillis()
            _sqlRequestId.value = UUID.randomUUID().toString()
            val results = SyntheticDataProvider.executeFederatedSql(query)
            _sqlExecutionTimeMs.value = System.currentTimeMillis() - startTime + 42L
            _sqlResults.value = results
        }
    }

    fun saveHMemContext(patientId: String, newContext: String) {
        viewModelScope.launch {
            val existing = hMemDao.getPatientMemory(patientId)
            val time = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(Date())
            val updatedString = if (existing != null) {
                "${existing.contextString}\n[$time Update]: $newContext"
            } else {
                "[$time Intake]: $newContext"
            }
            hMemDao.savePatientMemory(
                HMemEntity(
                    patientId = patientId,
                    contextString = updatedString,
                    updatedAt = time,
                    sessionCount = (existing?.sessionCount ?: 0) + 1
                )
            )
        }
    }

    /**
     * Executes the end-to-end multi-step Agent Pipeline
     * mimicking the Python agent loop
     */
    fun runAgentDiagnosis() {
        if (_isAgentRunning.value) return

        viewModelScope.launch {
            _isAgentRunning.value = true
            _finalDiagnosis.value = null

            val p = _selectedPatient.value
            val sym = _symptoms.value
            val rdt = _rdtStatus.value
            val micro = _microscopyStatus.value

            val steps = mutableListOf(
                AgentExecutionStep(
                    stepIndex = 1,
                    tag = "H-MEM",
                    title = "Memory Retrieval (H-MEM Engine)",
                    status = StepStatus.RUNNING,
                    subtitle = "Querying local SQLite persistent store for Patient ${p.patientId}...",
                    details = "SELECT context_string FROM patient_memory WHERE patient_id = '${p.patientId}';"
                ),
                AgentExecutionStep(
                    stepIndex = 2,
                    tag = "ZETARIS",
                    title = "Federated SQL Tool Call",
                    status = StepStatus.PENDING,
                    subtitle = "Federating S3 patients & regional epidemiology...",
                    details = ""
                ),
                AgentExecutionStep(
                    stepIndex = 3,
                    tag = "NIGHTSHIFT",
                    title = "NVIDIA Nemotron Reasoning",
                    status = StepStatus.PENDING,
                    subtitle = "Synthesizing symptoms, vision test & endemicity...",
                    details = ""
                ),
                AgentExecutionStep(
                    stepIndex = 4,
                    tag = "H-MEM-SAVE",
                    title = "Persistent Memory Commit",
                    status = StepStatus.PENDING,
                    subtitle = "Committing encounter note to longitudinal database...",
                    details = ""
                )
            )
            _executionSteps.value = steps.toList()

            // Step 1: H-MEM Retrieval
            delay(500)
            val memory = hMemDao.getPatientMemory(p.patientId)
            val memoryDetails = memory?.contextString ?: "No previous session recorded. Initial intake profile initialized."
            steps[0] = steps[0].copy(
                status = StepStatus.SUCCESS,
                subtitle = if (memory != null) "Retrieved ${memory.sessionCount} past clinical sessions" else "Fresh intake intake created",
                details = "H-MEM Retrieved Context:\n$memoryDetails"
            )
            steps[1] = steps[1].copy(status = StepStatus.RUNNING)
            _executionSteps.value = steps.toList()

            // Step 2: Zetaris SQL Tool Call
            delay(600)
            val sqlQuery = "SELECT p.patient_id, p.village, p.family_history, e.endemic_zone, e.active_cases " +
                    "FROM patients p JOIN regional_epidemiology e ON p.village = e.village " +
                    "WHERE p.patient_id = '${p.patientId}' OR p.village = '${p.village}';"
            val rows = SyntheticDataProvider.executeFederatedSql(sqlQuery)
            val sqlDetails = "POST /api/v1.0/sql-editor/sqls/run\n" +
                    "X-Request-ID: ${UUID.randomUUID()}\n" +
                    "X-Org-ID: 1\n" +
                    "Query: $sqlQuery\n" +
                    "Rows Returned: ${rows.size} records joined."
            steps[1] = steps[1].copy(
                status = StepStatus.SUCCESS,
                subtitle = "Executed cross-join query (${rows.size} rows returned)",
                details = sqlDetails
            )
            steps[2] = steps[2].copy(status = StepStatus.RUNNING)
            _executionSteps.value = steps.toList()

            // Step 3: Nightshift LLM (NVIDIA Nemotron 30B / 120B)
            delay(800)
            val audit = NightshiftAudit(
                targetModel = "nvidia/nemotron-3.5-lightning-30b-a3b",
                executedModel = "nvidia/nemotron-3-super-120b-a12b",
                routingLane = "nvidia-accelerated-lane-a3b",
                latencyMs = 384L,
                tokensPerSec = 118
            )
            val auditDetails = "Model: ${audit.executedModel}\n" +
                    "Routing Lane: ${audit.routingLane}\n" +
                    "Latency: ${audit.latencyMs}ms | Speed: ${audit.tokensPerSec} tok/s\n" +
                    "Headers: ${audit.appHeader} | ${audit.scopeHeader}"
            steps[2] = steps[2].copy(
                status = StepStatus.SUCCESS,
                subtitle = "Synthesized clinical guidance via ${audit.executedModel}",
                details = auditDetails
            )
            steps[3] = steps[3].copy(status = StepStatus.RUNNING)
            _executionSteps.value = steps.toList()

            // Step 4: H-MEM Update
            delay(400)
            val time = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(Date())
            val encounterNote = "Temp: ${sym.feverTemp}°C, Chills: ${sym.chills}, Vomiting: ${sym.vomiting} | " +
                    "RDT: ${if (rdt.isPositive) "POSITIVE" else "NEGATIVE"} | " +
                    "Microscopy: ${micro.parasitesPerMicroLiter} / μL | " +
                    "Prescribed Artemether-Lumefantrine 6-dose regimen"
            saveHMemContext(p.patientId, encounterNote)

            steps[3] = steps[3].copy(
                status = StepStatus.SUCCESS,
                subtitle = "Saved encounter note to H-MEM (session count incremented)",
                details = "Saved Context Delta:\n[$time Update]: $encounterNote"
            )
            _executionSteps.value = steps.toList()

            // Prepare Final Diagnosis Output
            val zone = SyntheticDataProvider.regionalEpidemiology.find { it.village.equals(p.village, ignoreCase = true) }
            val summary = if (rdt.isPositive) {
                "Patient ${p.name} from ${p.village} (${zone?.endemicZone ?: "High"} Endemic Zone, ${zone?.activeCases ?: 42} active cases) " +
                        "presents with confirmed acute Plasmodium falciparum infection. Hyperpyrexia (${sym.feverTemp}°C) with ${sym.durationDays}-day duration, " +
                        "chills, and body pain. Rapid Diagnostic Test shows reactive HRP-2 band. Microscopy demonstrates classic ring-form trophozoites (${micro.parasitesPerMicroLiter}/μL)."
            } else {
                "Patient ${p.name} from ${p.village} tested negative for malaria antigens on RDT. Presenting symptoms (${sym.feverTemp}°C fever) " +
                        "require differential evaluation for viral fever, typhoid, or respiratory infection. Do not initiate antimalarials without confirmed parasite etiology."
            }

            val actPrescription = if (rdt.isPositive) {
                "Artemether 20mg / Lumefantrine 120mg (Coartem) - 4 tablets stat at hour 0, 4 tablets at 8 hours, then 4 tablets BID on Days 2 & 3 (total 24 tablets)."
            } else {
                "Antimalarials withholding advised. Re-evaluate with repeat blood film if fever persists past 24 hours."
            }

            val result = DiagnosisResult(
                patientId = p.patientId,
                clinicalSummary = summary,
                prescriptionAct = actPrescription,
                supportiveCare = "Paracetamol 1000mg PO TDS for 48h for fever (${sym.feverTemp}°C); Oral Rehydration Salts (ORS) for fluid loss.",
                dangerSigns = listOf(
                    "Impaired consciousness, lethargy, or extreme prostration",
                    "Persistent vomiting preventing oral medication ingestion",
                    "Respiratory distress, deep acidotic breathing, or convulsions",
                    "Dark/black-water urine or clinical jaundice (urgent referral for IV Artesunate)"
                ),
                sqlQuery = sqlQuery,
                sqlRowsReturned = rows.size,
                hMemBefore = memoryDetails,
                hMemSavedNote = encounterNote,
                audit = audit
            )

            _finalDiagnosis.value = result
            _isAgentRunning.value = false
        }
    }
}
