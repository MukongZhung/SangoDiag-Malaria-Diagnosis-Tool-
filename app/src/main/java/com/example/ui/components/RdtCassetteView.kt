package com.example.ui.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun RdtCassetteView(
    isPositive: Boolean,
    modifier: Modifier = Modifier,
    onToggleResult: ((Boolean) -> Unit)? = null
) {
    val controlLineColor = Color(0xFFC2185B) // Vibrant pink/magenta control line
    val testLineColor by animateColorAsState(
        targetValue = if (isPositive) Color(0xFFC2185B) else Color(0x15000000),
        label = "test_line_color"
    )

    Card(
        modifier = modifier
            .fillMaxWidth()
            .testTag("rdt_cassette_card"),
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
                        text = "Rapid Diagnostic Test (RDT) Cassette",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "HRP-2 / pLDH Antigen Detection Strip",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                AssistChip(
                    onClick = { onToggleResult?.invoke(!isPositive) },
                    label = {
                        Text(
                            text = if (isPositive) "POSITIVE" else "NEGATIVE",
                            fontWeight = FontWeight.Bold,
                            color = if (isPositive) Color(0xFFB71C1C) else Color(0xFF1B5E20)
                        )
                    },
                    colors = AssistChipDefaults.assistChipColors(
                        containerColor = if (isPositive) Color(0xFFFFEBEE) else Color(0xFFE8F5E9)
                    ),
                    modifier = Modifier.testTag("rdt_toggle_chip")
                )
            }

            Spacer(modifier = Modifier.height(14.dp))

            // Realistic Physical Cassette Casing
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(95.dp)
                    .shadow(4.dp, RoundedCornerShape(12.dp))
                    .clip(RoundedCornerShape(12.dp))
                    .background(
                        Brush.verticalGradient(
                            listOf(Color(0xFFFBFBFB), Color(0xFFEBEBEB), Color(0xFFE0E0E0))
                        )
                    )
                    .border(1.dp, Color(0xFFCCCCCC), RoundedCornerShape(12.dp))
                    .padding(horizontal = 14.dp, vertical = 10.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxSize(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    // Left Brand & Wells Info
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center,
                        modifier = Modifier.width(60.dp)
                    ) {
                        Text(
                            text = "Pf/Pan",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Black,
                            color = Color(0xFF555555),
                            fontFamily = FontFamily.Monospace
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        // Sample Well (S)
                        Box(
                            modifier = Modifier
                                .size(34.dp)
                                .shadow(2.dp, RoundedCornerShape(17.dp))
                                .clip(RoundedCornerShape(17.dp))
                                .background(Color(0xFFD6D6D6))
                                .border(1.5.dp, Color(0xFF9E9E9E), RoundedCornerShape(17.dp)),
                            contentAlignment = Alignment.Center
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(24.dp)
                                    .clip(RoundedCornerShape(12.dp))
                                    .background(
                                        Brush.radialGradient(
                                            listOf(Color(0xFF8B0000), Color(0xFF5A0000))
                                        )
                                    )
                            )
                        }
                        Text(
                            text = "S",
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFF444444)
                        )
                    }

                    // Center: Nitrocellulose Membrane Reading Window
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .height(58.dp)
                            .padding(horizontal = 10.dp)
                            .shadow(2.dp, RoundedCornerShape(6.dp))
                            .clip(RoundedCornerShape(6.dp))
                            .background(Color(0xFFF9F7F1)) // Membrane off-white
                            .border(1.dp, Color(0xFFBDBDBD), RoundedCornerShape(6.dp))
                    ) {
                        // Lines canvas: C (Control) and T (Test)
                        Canvas(modifier = Modifier.fillMaxSize()) {
                            val width = size.width
                            val height = size.height

                            // Draw Control Line (C)
                            val cX = width * 0.40f
                            drawRoundRect(
                                color = controlLineColor,
                                topLeft = Offset(cX - 4f, height * 0.15f),
                                size = Size(8f, height * 0.70f),
                                cornerRadius = CornerRadius(2f, 2f)
                            )

                            // Draw Test Line (T)
                            val tX = width * 0.65f
                            drawRoundRect(
                                color = testLineColor,
                                topLeft = Offset(tX - 4f, height * 0.15f),
                                size = Size(8f, height * 0.70f),
                                cornerRadius = CornerRadius(2f, 2f)
                            )
                        }

                        // Labels above canvas
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 12.dp, vertical = 2.dp),
                            horizontalArrangement = Arrangement.SpaceAround
                        ) {
                            Text(
                                text = "C",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.ExtraBold,
                                color = Color(0xFF616161)
                            )
                            Text(
                                text = "T",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.ExtraBold,
                                color = Color(0xFF616161)
                            )
                        }
                    }

                    // Right: Buffer Well (B)
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center,
                        modifier = Modifier.width(60.dp)
                    ) {
                        Text(
                            text = "RDT-26",
                            fontSize = 10.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = Color(0xFF757575)
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        Box(
                            modifier = Modifier
                                .size(28.dp)
                                .shadow(2.dp, RoundedCornerShape(14.dp))
                                .clip(RoundedCornerShape(14.dp))
                                .background(Color(0xFFE0E0E0))
                                .border(1.5.dp, Color(0xFFAAAAAA), RoundedCornerShape(14.dp)),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = "B",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                color = Color(0xFF616161)
                            )
                        }
                        Text(
                            text = "Buffer",
                            fontSize = 9.sp,
                            color = Color(0xFF757575)
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Interpretation note
            Text(
                text = if (isPositive)
                    "✓ Valid Test: C & T bands visible -> Acute Plasmodium falciparum infection detected."
                else
                    "✓ Valid Test: Control (C) band only -> No Plasmodium antigens detected.",
                style = MaterialTheme.typography.bodySmall,
                color = if (isPositive) Color(0xFFC2185B) else Color(0xFF2E7D32),
                fontWeight = FontWeight.Medium
            )
        }
    }
}
