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

    private fun buildSymptomsText(sym: SymptomsState): String {
        val signs = listOfNotNull(
            "headache".takeIf { sym.headache },
            "body pain".takeIf { sym.bodyPain },
            "chills".takeIf { sym.chills },
            "vomiting".takeIf { sym.vomiting }
        )
        return "Fever (${sym.feverTemp}°C)" +
                (if (signs.isNotEmpty()) ", ${signs.joinToString(", ")}" else "") +
                " for ${sym.durationDays} days"
    }

    private fun buildTestText(rdt: RdtStatus): String =
        "RDT Cassette: ${rdt.antigen} line ${if (rdt.isPositive) "positive" else "negative"}" +
                (if (rdt.hasControlLine) ", control line valid" else ", control line missing (invalid test)")

    /** Returns null on success, or the reason the backend could not be used. */
    private suspend fun runBackendDiagnosis(): String? {
        val p = _selectedPatient.value
        val steps = mutableListOf(
            AgentExecutionStep(1, "H-MEM", "Memory Retrieval (H-MEM Engine)", StepStatus.RUNNING,
                "Backend: reading persistent memory for ${p.patientId}..."),
            AgentExecutionStep(2, "ZETARIS", "Federated SQL Tool Call", StepStatus.RUNNING,
                "Backend: querying patient record & village epidemiology..."),
            AgentExecutionStep(3, "NIGHTSHIFT", "NVIDIA Nemotron Reasoning", StepStatus.RUNNING,
                "Backend: running the agent loop..."),
            AgentExecutionStep(4, "H-MEM-SAVE", "Persistent Memory Commit", StepStatus.PENDING,
                "Waiting for diagnosis...")
        )
        _executionSteps.value = steps.toList()

        val started = System.currentTimeMillis()
        val resp = try {
            AgentApi.create(_agentBaseUrl.value).diagnose(
                DiagnoseRequest(
                    patientId = p.patientId,
                    symptoms = buildSymptomsText(_symptoms.value),
                    imageResult = buildTestText(_rdtStatus.value)
                )
            )
        } catch (e: Exception) {
            return "Backend ${_agentBaseUrl.value} unreachable (${e.javaClass.simpleName}: ${e.message})"
        }
        val elapsed = System.currentTimeMillis() - started

        val a = resp.assessment
        val lastCall = resp.llmCalls.lastOrNull()
        val online = resp.llmCalls.any { it.mode == "nightshift" }
        val audit = NightshiftAudit(
            targetModel = _meterlessModel.value,
            executedModel = lastCall?.executedModel ?: "not reported",
            routingLane = lastCall?.routingLane ?: "not reported",
            latencyMs = elapsed,
            mode = if (online) "Nightshift" else "Backend offline rules"
        )

        steps[0] = steps[0].copy(
            status = StepStatus.SUCCESS,
            subtitle = if (resp.memoryBefore != null) "Prior sessions found" else "No prior session (new intake)",
            details = "H-MEM Retrieved Context:\n${resp.memoryBefore ?: "None"}"
        )
        steps[1] = steps[1].copy(
            status = StepStatus.SUCCESS,
            subtitle = "${resp.sqlQueries.size} query(ies), ${resp.sqlRows.size} row(s) returned",
            details = resp.sqlQueries.joinToString("\n\n")
        )
        steps[2] = steps[2].copy(
            status = StepStatus.SUCCESS,
            subtitle = "${resp.llmCalls.size} turn(s) · ${audit.mode}",
            details = resp.llmCalls.joinToString("\n") {
                "Turn: ${it.mode} | model=${it.executedModel ?: "?"} | ${it.latencyMs}ms"
            }
        )
        steps[3] = steps[3].copy(
            status = StepStatus.SUCCESS,
            subtitle = "Encounter note saved to H-MEM",
            details = "Saved Context Delta:\n${resp.memorySavedNote}"
        )
        _executionSteps.value = steps.toList()

        // Mirror the note locally so the H-MEM screen reflects the backend session
        saveHMemContext(p.patientId, resp.memorySavedNote)

        val prescription = a.coartemTabletsPerDose?.let { "${a.treatment} - $it tablet(s) per dose" } ?: a.treatment
        val temp = a.temperature
        _finalDiagnosis.value = DiagnosisResult(
            patientId = resp.patientId,
            badgeLabel = when {
                a.isSevere -> "SEVERE malaria"
                a.testResult == "positive" -> "P. falciparum (+)"
                a.testResult == "negative" -> "Malaria (-)"
                else -> "Not confirmed"
            },
            testPositive = a.testResult == "positive",
            isSevere = a.isSevere,
            clinicalSummary = resp.report.replace("**", "").replace("### ", ""),
            prescriptionAct = prescription,
            supportiveCare = if (temp != null && temp > 38.5 && !a.isSevere)
                "Paracetamol 15 mg/kg (adult 1 g) every 6 hours; oral rehydration salts (ORS)."
            else "Clinical monitoring; follow the referral plan if danger signs appear.",
            dangerSigns = if (a.severeSigns.isNotEmpty()) a.severeSigns.map { "DETECTED: $it" } else STANDARD_DANGER_SIGNS,
            sqlQuery = resp.sqlQueries.lastOrNull() ?: "",
            sqlRowsReturned = resp.sqlRows.size,
            hMemBefore = resp.memoryBefore,
            hMemSavedNote = resp.memorySavedNote,
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
                "Artemether 20mg / Lumefantrine 120mg (Coartem) - 4 tablets stat at hour 0, 4 tablets at 8 hours, then 4 tablets BID on Days 2 & 3 (total 24 tablets)."
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
                supportiveCare = "Paracetamol 1000mg PO TDS for 48h for fever (${sym.feverTemp}°C); Oral Rehydration Salts (ORS) for fluid loss.",
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
