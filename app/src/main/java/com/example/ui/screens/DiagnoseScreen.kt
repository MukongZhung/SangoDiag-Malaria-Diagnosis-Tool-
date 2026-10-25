package com.example.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.data.models.Patient
import com.example.ui.components.AgentExecutionCard
import com.example.ui.components.FinalDiagnosisReportView
import com.example.ui.components.MicroscopyView
import com.example.ui.components.RdtCassetteView
import com.example.ui.theme.HighRiskRed
import com.example.ui.theme.MediumRiskAmber
import com.example.ui.viewmodel.MainViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DiagnoseScreen(
    viewModel: MainViewModel,
    modifier: Modifier = Modifier
) {
    val selectedPatient by viewModel.selectedPatient.collectAsState()
    val symptoms by viewModel.symptoms.collectAsState()
    val rdtStatus by viewModel.rdtStatus.collectAsState()
    val microscopyStatus by viewModel.microscopyStatus.collectAsState()
    val isRunning by viewModel.isAgentRunning.collectAsState()
    val executionSteps by viewModel.executionSteps.collectAsState()
    val finalDiagnosis by viewModel.finalDiagnosis.collectAsState()

    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        contentPadding = PaddingValues(top = 16.dp, bottom = 32.dp)
    ) {
        // Hero Header
        item {
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f)
                ),
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(48.dp)
                            .clip(RoundedCornerShape(12.dp))
                            .background(MaterialTheme.colorScheme.primary),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Default.Biotech,
                            contentDescription = "Diagnostic AI",
                            tint = Color.White,
                            modifier = Modifier.size(28.dp)
                        )
                    }
                    Spacer(modifier = Modifier.width(14.dp))
                    Column {
                        Text(
                            text = "AI Malaria Clinical Station",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = "Meterless Nightshift + Zetaris + H-MEM Engine",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
        }

        // Section: Patient Intake
        item {
            Column {
                Text(
                    text = "1. Patient Intake & Village Location",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )
                Spacer(modifier = Modifier.height(8.dp))

                LazyRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    items(viewModel.patients) { p: Patient ->
                        val isSelected = p.patientId == selectedPatient.patientId
                        FilterChip(
                            selected = isSelected,
                            onClick = { viewModel.selectPatient(p) },
                            label = {
                                Text("${p.name} (${p.village})")
                            },
                            leadingIcon = if (isSelected) {
                                {
                                    Icon(
                                        imageVector = Icons.Default.Check,
                                        contentDescription = "Selected",
                                        modifier = Modifier.size(16.dp)
                                    )
                                }
                            } else null,
                            modifier = Modifier.testTag("patient_chip_${p.patientId}")
                        )
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                // Patient Info Card
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(
                                text = "ID: ${selectedPatient.patientId} | ${selectedPatient.age} yrs (${selectedPatient.gender})",
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.SemiBold
                            )
                            Text(
                                text = "Village: ${selectedPatient.village} (Cameroon) | Phone: ${selectedPatient.phone}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }

                        AssistChip(
                            onClick = {},
                            label = {
                                Text(
                                    text = if (selectedPatient.familyHistory) "Fam History (+)" else "No Fam History",
                                    fontSize = 11.sp
                                )
                            }
                        )
                    }
                }
            }
        }

        // Section: Vitals & Presenting Symptoms
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f)
                )
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp)
                ) {
                    Text(
                        text = "2. Clinical Presentation & Vitals",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    // Temperature Slider
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "Body Temperature:",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium
                        )
                        val tempColor = if (symptoms.feverTemp >= 39.0f) HighRiskRed else if (symptoms.feverTemp >= 38.0f) MediumRiskAmber else MaterialTheme.colorScheme.primary
                        Text(
                            text = String.format("%.1f°C (Febrile)", symptoms.feverTemp),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = tempColor
                        )
                    }

                    Slider(
                        value = symptoms.feverTemp,
                        onValueChange = { viewModel.updateFeverTemp(it) },
                        valueRange = 36.5f..41.0f,
                        steps = 45,
                        modifier = Modifier.testTag("temp_slider")
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    Text(
                        text = "Reported Symptoms:",
                        style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )

                    Spacer(modifier = Modifier.height(6.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        FilterChip(
                            selected = symptoms.chills,
                            onClick = { viewModel.toggleSymptom(chills = !symptoms.chills) },
                            label = { Text("Chills / Rigors") },
                            modifier = Modifier.weight(1f)
                        )
                        FilterChip(
                            selected = symptoms.bodyPain,
                            onClick = { viewModel.toggleSymptom(bodyPain = !symptoms.bodyPain) },
                            label = { Text("Myalgia / Aches") },
                            modifier = Modifier.weight(1f)
                        )
                    }

                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 4.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        FilterChip(
                            selected = symptoms.headache,
                            onClick = { viewModel.toggleSymptom(headache = !symptoms.headache) },
                            label = { Text("Severe Headache") },
                            modifier = Modifier.weight(1f)
                        )
                        FilterChip(
                            selected = symptoms.vomiting,
                            onClick = { viewModel.toggleSymptom(vomiting = !symptoms.vomiting) },
                            label = { Text("Nausea / Vomiting") },
                            modifier = Modifier.weight(1f)
                        )
                    }
                }
            }
        }

        // Section: Rapid Diagnostic Test & Microscopy
        item {
            Column {
                Text(
                    text = "3. Field Parasitological Diagnostics",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )
                Spacer(modifier = Modifier.height(8.dp))

                RdtCassetteView(
                    isPositive = rdtStatus.isPositive,
                    onToggleResult = { viewModel.toggleRdtResult(it) }
                )

                Spacer(modifier = Modifier.height(12.dp))

                MicroscopyView(
                    parasiteDensity = microscopyStatus.parasitesPerMicroLiter,
                    species = microscopyStatus.species
                )
            }
        }

        // Section: Primary Action CTA
        item {
            Button(
                onClick = { viewModel.runAgentDiagnosis() },
                enabled = !isRunning,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(54.dp)
                    .testTag("run_agent_diagnosis_button"),
                shape = RoundedCornerShape(14.dp)
            ) {
                if (isRunning) {
                    CircularProgressIndicator(
                        color = MaterialTheme.colorScheme.onPrimary,
                        modifier = Modifier.size(22.dp),
                        strokeWidth = 2.5.dp
                    )
                    Spacer(modifier = Modifier.width(12.dp))
                    Text(
                        text = "Orchestrating Agent Loop...",
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold
                    )
                } else {
                    Icon(imageVector = Icons.Default.PlayArrow, contentDescription = "Run")
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "Diagnose with AI Agent (Nemotron + Zetaris)",
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }

        // Section: Real-time Multi-step Agent Execution Cards
        if (executionSteps.isNotEmpty()) {
            item {
                Text(
                    text = "Agent Execution Trace",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )
            }

            items(executionSteps) { step ->
                AgentExecutionCard(step = step)
            }
        }

        // Section: Final Grounded Report
        if (finalDiagnosis != null) {
            item {
                FinalDiagnosisReportView(result = finalDiagnosis!!)
            }
        }
    }
}
