package com.example.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.viewmodel.MainViewModel

@Composable
fun SettingsScreen(
    viewModel: MainViewModel,
    modifier: Modifier = Modifier
) {
    val meterlessUrl by viewModel.meterlessBaseUrl.collectAsState()
    val meterlessToken by viewModel.meterlessToken.collectAsState()
    val meterlessModel by viewModel.meterlessModel.collectAsState()
    val zetarisUrl by viewModel.zetarisBaseUrl.collectAsState()
    val zetarisApiKey by viewModel.zetarisApiKey.collectAsState()
    val autonomousMode by viewModel.autonomousFieldMode.collectAsState()
    val agentBaseUrl by viewModel.agentBaseUrl.collectAsState()

    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        contentPadding = PaddingValues(top = 16.dp, bottom = 32.dp)
    ) {
        item {
            Text(
                text = "Runtime & Platform Settings",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary
            )
        }

        // Autonomous Offline Mode Card
        item {
            Card(
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.4f)
                ),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Autonomous Field Engine (Offline)",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Runs an on-device rule-based simulation instead of calling the agent backend. Use it in clinics without connectivity. When off, the app falls back to it automatically if the backend is unreachable.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Switch(
                        checked = autonomousMode,
                        onCheckedChange = { viewModel.setAutonomousFieldMode(it) },
                        modifier = Modifier.testTag("autonomous_mode_switch")
                    )
                }
            }
        }

        // Agent Backend (Python API) Config
        item {
            Card(
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "Agent Backend (agent/api.py)",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Emulator: http://10.0.2.2:8000/ · Phone on the same Wi-Fi: http://<PC-IP>:8000/",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    OutlinedTextField(
                        value = agentBaseUrl,
                        onValueChange = { viewModel.setAgentBaseUrl(it) },
                        label = { Text("AGENT_BASE_URL") },
                        singleLine = true,
                        enabled = !autonomousMode,
                        modifier = Modifier
                            .fillMaxWidth()
                            .testTag("agent_base_url_field")
                    )
                }
            }
        }

        // Nightshift Power Layer Config
        item {
            Card(
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "Meterless Nightshift (Power Layer)",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = meterlessUrl,
                        onValueChange = {},
                        label = { Text("METERLESS_BASE_URL") },
                        modifier = Modifier.fillMaxWidth(),
                        readOnly = true
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    OutlinedTextField(
                        value = meterlessModel,
                        onValueChange = {},
                        label = { Text("METERLESS_MODEL") },
                        modifier = Modifier.fillMaxWidth(),
                        readOnly = true
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    OutlinedTextField(
                        value = meterlessToken,
                        onValueChange = {},
                        label = { Text("METERLESS_RUNTIME_TOKEN") },
                        modifier = Modifier.fillMaxWidth(),
                        readOnly = true
                    )
                }
            }
        }

        // Zetaris Data Layer Config
        item {
            Card(
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "Zetaris REST API (Data Layer)",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = zetarisUrl,
                        onValueChange = {},
                        label = { Text("ZETARIS_BASE_URL") },
                        modifier = Modifier.fillMaxWidth(),
                        readOnly = true
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    OutlinedTextField(
                        value = zetarisApiKey,
                        onValueChange = {},
                        label = { Text("ZETARIS_API_KEY") },
                        modifier = Modifier.fillMaxWidth(),
                        readOnly = true
                    )
                }
            }
        }

        // Clinical Guidelines Compliance Info
        item {
            Card(
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f)
                ),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "Clinical Protocols & Standards",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        text = "• Cameroon Ministry of Public Health (MINSANTE) Malaria Treatment Guidelines\n" +
                               "• WHO Guidelines for Malaria Diagnosis & Treatment (6-dose Artemether-Lumefantrine)\n" +
                               "• Built for Hackathon Tracks: Fragmented Data (Zetaris) & Grounded Reasoning (Nightshift/Nemotron)",
                        style = MaterialTheme.typography.bodySmall,
                        lineHeight = 18.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}
