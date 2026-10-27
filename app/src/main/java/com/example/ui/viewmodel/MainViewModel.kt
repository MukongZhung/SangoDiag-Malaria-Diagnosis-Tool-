package com.example.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.data.SyntheticDataProvider
import com.example.data.local.AppDatabase
import com.example.data.local.HMemEntity
import com.example.data.models.*
import com.example.data.remote.AgentApi
import com.example.data.remote.DiagnoseRequest
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
    private val _currentSql = MutableStateFlow("SELECT p.patient_id, p.age, p.village, p.family_history_malaria, e.endemic_zone, e.active_cases_this_week FROM patients p JOIN regional_epidemiology e ON p.village = e.village WHERE e.endemic_zone = 'High';")
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

    private val _autonomousFieldMode = MutableStateFlow(false)
    val autonomousFieldMode: StateFlow<Boolean> = _autonomousFieldMode.asStateFlow()

    // Python agent API (agent/api.py). 10.0.2.2 is the host PC as seen from the Android emulator.
    private val _agentBaseUrl = MutableStateFlow("http://10.0.2.2:8000/")
    val agentBaseUrl: StateFlow<String> = _agentBaseUrl.asStateFlow()

    init {
        // H-MEM starts empty: records are created by real diagnosis sessions
        viewModelScope.launch {
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

    fun setAutonomousFieldMode(enabled: Boolean) {
        _autonomousFieldMode.value = enabled
    }

    fun setAgentBaseUrl(url: String) {
        _agentBaseUrl.value = url.trim()
    }

    /**
     * Executes the end-to-end multi-step Agent Pipeline.
     * Online: calls the Python agent API (agent/api.py), which runs the real loop.
     * Field mode, or backend unreachable: on-device simulation with the same steps.
     */
    fun runAgentDiagnosis() {
        if (_isAgentRunning.value) return

        viewModelScope.launch {
            _isAgentRunning.value = true
            _finalDiagnosis.value = null
            try {
                val fallbackReason = if (_autonomousFieldMode.value) null else runBackendDiagnosis()
                if (_autonomousFieldMode.value || fallbackReason != null) {
                    runLocalSimulation(fallbackReason)
                }
            } finally {
                _isAgentRunning.value = false
            }
        }
    }

    private fun buildRequest(p: Patient, sym: SymptomsState, rdt: RdtStatus): DiagnoseRequest {
        val symptoms = listOfNotNull(
            "fever".takeIf { sym.feverTemp >= 37.5f },
            "headache".takeIf { sym.headache },
            "body_pain".takeIf { sym.bodyPain },
            "chills".takeIf { sym.chills },
            "vomiting".takeIf { sym.vomiting }
        )
        val test = when {
            !rdt.hasControlLine -> "inconclusive"
            rdt.isPositive -> "rdt_positive"
            else -> "rdt_negative"
        }
        return DiagnoseRequest(
            patientId = p.patientId,
            temperatureC = sym.feverTemp.toDouble(),
            feverDays = sym.durationDays,
            ageYears = p.age.toDouble(),
            symptoms = symptoms,
            recentTravel = p.recentTravel,
            testResult = test
        )
    }

    /** Returns null on success, or the reason the backend could not be used. */
    private suspend fun runBackendDiagnosis(): String? {
        val p = _selectedPatient.value
        val steps = mutableListOf(
            AgentExecutionStep(1, "H-MEM", "Memory Recall (H-MEM Engine)", StepStatus.RUNNING,
                "Backend: ranking what H-MEM remembers about ${p.patientId}..."),
            AgentExecutionStep(2, "ZETARIS", "Planner SQL on Zetaris", StepStatus.RUNNING,
                "Backend: planner (fast lane) fetching record & village epidemiology..."),
            AgentExecutionStep(3, "NIGHTSHIFT", "Rules + Nemotron Report", StepStatus.RUNNING,
                "Backend: triage rules, then reporter (deep lane) checked by the critic..."),
            AgentExecutionStep(4, "H-MEM-SAVE", "Persistent Memory Commit", StepStatus.PENDING,
                "Waiting for the decision...")
        )
        _executionSteps.value = steps.toList()

        val resp = try {
            AgentApi.create(_agentBaseUrl.value).diagnose(buildRequest(p, _symptoms.value, _rdtStatus.value))
        } catch (e: Exception) {
            return "Backend ${_agentBaseUrl.value} unreachable (${e.javaClass.simpleName}: ${e.message})"
        }
        val tr = resp.triage
        if (resp.error != null || tr == null) {
            return "Backend run stopped: ${resp.error ?: "no triage result"}"
        }

        val lastCall = resp.calls.lastOrNull()
        val online = resp.calls.any { it.live }
        val audit = NightshiftAudit(
            targetModel = _meterlessModel.value,
            executedModel = lastCall?.modelReported ?: "not reported",
            routingLane = lastCall?.lane ?: "n/a",
            latencyMs = (resp.elapsedS * 1000).toLong(),
            mode = if (online) "Nightshift" else "Offline simulator"
        )

        val recalled = resp.memory.items.joinToString("\n") { "[${it.`when`}] ${it.content}" }
        steps[0] = steps[0].copy(
            status = StepStatus.SUCCESS,
            subtitle = if (resp.memory.count > 0) "${resp.memory.count} memory item(s) recalled" else "No prior memory (new patient)",
            details = "H-MEM Recalled:\n${recalled.ifEmpty { "None" }}"
        )
        steps[1] = steps[1].copy(
            status = StepStatus.SUCCESS,
            subtitle = "${resp.queries.size} query(ies) · ${resp.queries.sumOf { it.rows.size }} row(s)",
            details = resp.queries.joinToString("\n\n") { "[${it.qid ?: "Q?"}] (${it.askedBy ?: "?"}, ${it.source}) ${it.sql}" }
        )
        steps[2] = steps[2].copy(
            status = StepStatus.SUCCESS,
            subtitle = "${tr.actionLabel} · score ${tr.score}/100 · ${audit.mode}",
            details = resp.calls.joinToString("\n") { "${it.role} [${it.lane}] model=${it.modelReported} ${it.latencyMs}ms" }
        )
        steps[3] = steps[3].copy(
            status = StepStatus.SUCCESS,
            subtitle = "${resp.memoryWritten.size} record(s) saved to H-MEM",
            details = "Report source: ${resp.reportSource}"
        )
        _executionSteps.value = steps.toList()

        // Mirror the decision locally so the H-MEM screen reflects the backend session
        val note = "${tr.actionLabel} (malaria score ${tr.score}/100, confidence ${tr.confidence})"
        saveHMemContext(p.patientId, note)

        val rdt = _rdtStatus.value
        _finalDiagnosis.value = DiagnosisResult(
            patientId = p.patientId,
            badgeLabel = tr.actionLabel,
            testPositive = rdt.hasControlLine && rdt.isPositive,
            isSevere = tr.urgent,
            clinicalSummary = resp.report.replace("**", "").ifEmpty { tr.nextSteps.joinToString("\n") },
            prescriptionAct = "${tr.actionLabel} (score ${tr.score}/100, ${tr.level}, confidence ${tr.confidence})" +
                    (if (tr.abstain) " - evidence too thin, decision withheld" else ""),
            supportiveCare = tr.nextSteps.joinToString(" ").ifEmpty { "Follow the national protocol chart." },
            dangerSigns = if (tr.urgent) listOf("DANGER SIGN PRESENT: refer urgently") + STANDARD_DANGER_SIGNS else STANDARD_DANGER_SIGNS,
            sqlQuery = resp.queries.lastOrNull()?.sql ?: "",
            sqlRowsReturned = resp.queries.sumOf { it.rows.size },
            hMemBefore = recalled.ifEmpty { null },
            hMemSavedNote = note,
            audit = audit
        )
        return null
    }

    private suspend fun runLocalSimulation(fallbackReason: String?) {
        run {
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
            // No LLM is called on-device: say so instead of reporting a model
            val audit = NightshiftAudit(
                targetModel = _meterlessModel.value,
                executedModel = "none (on-device rules)",
                routingLane = "n/a",
                latencyMs = 0L,
                mode = "On-device simulation"
            )
            val auditDetails = "Mode: ${audit.mode}\n" +
                    (fallbackReason?.let { "Reason: $it\n" } ?: "Field mode enabled in Settings\n") +
                    "Headers (when online): ${audit.appHeader} | ${audit.scopeHeader}"
            steps[2] = steps[2].copy(
                status = StepStatus.SUCCESS,
                subtitle = "Rule-based guidance (no network)",
                details = auditDetails
            )
            steps[3] = steps[3].copy(status = StepStatus.RUNNING)
            _executionSteps.value = steps.toList()

            // Step 4: H-MEM Update
            delay(400)
            val time = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(Date())
            val encounterNote = "Temp: ${sym.feverTemp}°C, Chills: ${sym.chills}, Vomiting: ${sym.vomiting} | " +
                    "RDT: ${if (rdt.isPositive) "POSITIVE" else "NEGATIVE"} | " +
                    (if (rdt.isPositive) "Microscopy: ${micro.parasitesPerMicroLiter} / μL | Prescribed Artemether-Lumefantrine 6-dose regimen"
                    else "No antimalarial; investigate other causes of fever")
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
                "Treat per national protocol (first-line ACT). Doses: national protocol chart."
            } else {
                "Antimalarials withholding advised. Re-evaluate with repeat blood film if fever persists past 24 hours."
            }

            val result = DiagnosisResult(
                patientId = p.patientId,
                badgeLabel = if (rdt.isPositive) "P. falciparum (+)" else "Malaria (-)",
                testPositive = rdt.isPositive,
                isSevere = false,
                clinicalSummary = summary,
                prescriptionAct = actPrescription,
                supportiveCare = "Antipyretic and fluids per national protocol for fever (${sym.feverTemp}°C).",
                dangerSigns = STANDARD_DANGER_SIGNS,
                sqlQuery = sqlQuery,
                sqlRowsReturned = rows.size,
                hMemBefore = memoryDetails,
                hMemSavedNote = encounterNote,
                audit = audit
            )

            _finalDiagnosis.value = result
        }
    }

    companion object {
        val STANDARD_DANGER_SIGNS = listOf(
            "Impaired consciousness, lethargy, or extreme prostration",
            "Persistent vomiting preventing oral medication ingestion",
            "Respiratory distress, deep acidotic breathing, or convulsions",
            "Dark/black-water urine or clinical jaundice (urgent referral for IV Artesunate)"
        )
    }
}
