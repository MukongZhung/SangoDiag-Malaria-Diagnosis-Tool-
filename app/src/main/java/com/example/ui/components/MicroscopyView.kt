package com.example.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun MicroscopyView(
    parasiteDensity: Int,
    species: String,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .testTag("microscopy_card"),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = "Giemsa Blood Film Microscopy",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "100x Oil Immersion Optical Field",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                Badge(
                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                    contentColor = MaterialTheme.colorScheme.onPrimaryContainer
                ) {
                    Text(
                        text = "$parasiteDensity / μL",
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp
                    )
                }
            }

            Spacer(modifier = Modifier.height(14.dp))

            // Circular Microscope Viewport
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(150.dp),
                contentAlignment = Alignment.Center
            ) {
                Box(
                    modifier = Modifier
                        .size(140.dp)
                        .shadow(8.dp, CircleShape)
                        .clip(CircleShape)
                        .background(
                            Brush.radialGradient(
                                listOf(Color(0xFFF4EDF8), Color(0xFFDED0E8), Color(0xFFC7B1D6))
                            )
                        )
                        .border(4.dp, Color(0xFF37474F), CircleShape)
                ) {
                    // Draw Red Blood Cells and Plasmodium Ring forms
                    Canvas(modifier = Modifier.fillMaxSize()) {
                        val center = Offset(size.width / 2, size.height / 2)

                        // Draw background RBCs (pale pink discs)
                        val rbcColor = Color(0x60F8BBD0)
                        val rbcBorder = Color(0x80E91E63)
                        val rbcOffsets = listOf(
                            Offset(center.x - 35f, center.y - 25f),
                            Offset(center.x + 30f, center.y - 35f),
                            Offset(center.x - 20f, center.y + 35f),
                            Offset(center.x + 35f, center.y + 25f),
                            Offset(center.x + 5f, center.y - 10f),
                            Offset(center.x - 45f, center.y + 15f),
                            Offset(center.x + 40f, center.y - 5f)
                        )

                        for (pos in rbcOffsets) {
                            drawCircle(color = rbcColor, radius = 22f, center = pos)
                            drawCircle(color = rbcBorder, radius = 22f, center = pos, style = androidx.compose.ui.graphics.drawscope.Stroke(1.5f))
                        }

                        // Draw Plasmodium falciparum ring-form trophozoites (deep violet/blue rings with chromatin dot)
                        val ringColor = Color(0xFF4A148C) // Dark purple chromatin
                        val ringBorder = Color(0xFF6A1B9A)
                        val dotColor = Color(0xFF880E4F) // Magenta/red chromatin dot

                        val parasitePositions = listOf(
                            Offset(center.x - 30f, center.y - 20f),
                            Offset(center.x + 32f, center.y - 30f),
                            Offset(center.x + 2f, center.y - 8f)
                        )

                        for (p in parasitePositions) {
                            // Ring cytoplasm
                            drawCircle(
                                color = ringBorder,
                                radius = 7f,
                                center = p,
                                style = androidx.compose.ui.graphics.drawscope.Stroke(2f)
                            )
                            // Chromatin dot
                            drawCircle(
                                color = dotColor,
                                radius = 2.5f,
                                center = Offset(p.x + 5f, p.y - 4f)
                            )
                        }

                        // Microscope reticle crosshairs
                        drawLine(
                            color = Color(0x30000000),
                            start = Offset(center.x, 0f),
                            end = Offset(center.x, size.height),
                            strokeWidth = 1f
                        )
                        drawLine(
                            color = Color(0x30000000),
                            start = Offset(0f, center.y),
                            end = Offset(size.width, center.y),
                            strokeWidth = 1f
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            Text(
                text = "Species: $species",
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface
            )
            Text(
                text = "Trophozoites observed with classic delicate ring cytoplasm and prominent chromatin dots (~2.3% parasitemia).",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}
