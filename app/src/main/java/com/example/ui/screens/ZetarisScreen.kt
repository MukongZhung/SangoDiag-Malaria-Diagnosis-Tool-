package com.example.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.data.SyntheticDataProvider
import com.example.ui.theme.HighRiskRed
import com.example.ui.theme.LowRiskGreen
import com.example.ui.theme.MediumRiskAmber
import com.example.ui.viewmodel.MainViewModel

@Composable
fun ZetarisScreen(
    viewModel: MainViewModel,
    modifier: Modifier = Modifier
) {
    val currentSql by viewModel.currentSql.collectAsState()
    val sqlResults by viewModel.sqlResults.collectAsState()
    val sqlTimeMs by viewModel.sqlExecutionTimeMs.collectAsState()
    val requestId by viewModel.sqlRequestId.collectAsState()

    var queryInput by remember(currentSql) { mutableStateOf(currentSql) }
    val hScroll = rememberScrollState()

    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        contentPadding = PaddingValues(top = 16.dp, bottom = 32.dp)
    ) {
        // Architecture Header
        item {
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.45f)
                ),
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(40.dp)
                                .clip(RoundedCornerShape(10.dp))
                                .background(MaterialTheme.colorScheme.primary),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = Icons.Default.Dataset,
                                contentDescription = "Zetaris Data Layer",
                                tint = Color.White,
                                modifier = Modifier.size(22.dp)
                            )
                        }
                        Spacer(modifier = Modifier.width(12.dp))
                        Column {
                            Text(
                                text = "Zetaris Federated Data Studio",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Track 1: Fragmented Data Zero-ETL Federation",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(10.dp))

                    Text(
                        text = "Federates decentralized S3 clinical datasets (patients.csv, clinical_visits.csv) and local disease surveillance (regional_epidemiology.csv) via REST API SQL (/sql-editor/sqls/run). Generates fresh X-Request-ID UUIDs on each call.",
                        style = MaterialTheme.typography.bodySmall,
                        lineHeight = 18.sp,
                        color = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                }
            }
        }

        // Cameroon Endemicity Surveillance Overview
        item {
            Column {
                Text(
                    text = "Cameroon Regional Epidemiology Surveillance",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )
                Spacer(modifier = Modifier.height(8.dp))

                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(hScroll),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    SyntheticDataProvider.regionalEpidemiology.forEach { zone ->
                        val badgeColor = when (zone.endemicZone) {
                            "High" -> HighRiskRed
                            "Medium" -> MediumRiskAmber
                            else -> LowRiskGreen
                        }

                        Card(
                            modifier = Modifier.width(160.dp),
                            shape = RoundedCornerShape(12.dp),
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = zone.village,
                                        style = MaterialTheme.typography.titleSmall,
                                        fontWeight = FontWeight.Bold
                                    )
                                    Badge(containerColor = badgeColor.copy(alpha = 0.2f), contentColor = badgeColor) {
                                        Text(
                                            text = zone.endemicZone,
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 10.sp,
                                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                                        )
                                    }
                                }
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = zone.region,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Spacer(modifier = Modifier.height(8.dp))
                                Text(
                                    text = "Active cases this week: ${zone.activeCases} · Breeding risk: ${zone.breedingSiteRisk}",
                                    fontWeight = FontWeight.SemiBold,
                                    fontSize = 12.sp,
                                    color = MaterialTheme.colorScheme.primary
                                )
                            }
                        }
                    }
                }
            }
        }

        // Interactive SQL Editor Section
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp)
                ) {
                    Text(
                        text = "Interactive SQL Query Tool",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Spacer(modifier = Modifier.height(6.dp))

                    // Preset query buttons
                    Text(
                        text = "Sample Query Templates:",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        SuggestionChip(
                            onClick = {
                                queryInput = "SELECT * FROM regional_epidemiology WHERE endemic_zone = 'High';"
                                viewModel.setSqlQuery(queryInput)
                                viewModel.runSqlQuery(queryInput)
                            },
                            label = { Text("High Risk Zones", fontSize = 11.sp) }
                        )
                        SuggestionChip(
                            onClick = {
                                queryInput = "SELECT p.patient_id, p.village, e.endemic_zone, e.active_cases FROM patients p JOIN regional_epidemiology e ON p.village = e.village;"
                                viewModel.setSqlQuery(queryInput)
                                viewModel.runSqlQuery(queryInput)
                            },
                            label = { Text("Patients Cross-Join", fontSize = 11.sp) }
                        )
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    OutlinedTextField(
                        value = queryInput,
                        onValueChange = { queryInput = it },
                        modifier = Modifier
                            .fillMaxWidth()
                            .testTag("sql_input_field"),
                        label = { Text("Zetaris SQL Query") },
                        textStyle = LocalTextStyle.current.copy(
                            fontFamily = FontFamily.Monospace,
                            fontSize = 12.sp
                        ),
                        minLines = 3
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(
                                text = "X-Request-ID: ${requestId.take(16)}...",
                                fontFamily = FontFamily.Monospace,
                                fontSize = 10.sp,
                                color = MaterialTheme.colorScheme.outline
                            )
                            Text(
                                text = "Latency: ${sqlTimeMs}ms | Rows: ${sqlResults.size}",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.SemiBold,
                                color = MaterialTheme.colorScheme.primary
                            )
                        }

                        Button(
                            onClick = {
                                viewModel.setSqlQuery(queryInput)
                                viewModel.runSqlQuery(queryInput)
                            },
                            modifier = Modifier.testTag("run_sql_button")
                        ) {
                            Icon(imageVector = Icons.Default.PlayArrow, contentDescription = "Run SQL")
                            Spacer(modifier = Modifier.width(6.dp))
                            Text("Run SQL")
                        }
                    }
                }
            }
        }

        // Query Results Table
        item {
            Text(
                text = "Federated Query Results (${sqlResults.size} rows)",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary
            )
        }

        if (sqlResults.isEmpty()) {
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Box(modifier = Modifier.padding(20.dp), contentAlignment = Alignment.Center) {
                        Text("No records returned. Execute a query to view results.")
                    }
                }
            }
        } else {
            items(sqlResults) { row ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f))
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        row.entries.forEach { entry ->
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 2.dp),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(
                                    text = entry.key,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Text(
                                    text = entry.value,
                                    fontSize = 11.5.sp,
                                    fontFamily = FontFamily.Monospace,
                                    fontWeight = FontWeight.Medium,
                                    color = MaterialTheme.colorScheme.onSurface
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
