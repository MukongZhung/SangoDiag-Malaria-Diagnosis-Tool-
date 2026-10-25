package com.example

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.screens.*
import com.example.ui.theme.MyApplicationTheme
import com.example.ui.viewmodel.MainViewModel

enum class NavDestination(val label: String, val icon: ImageVector, val tag: String) {
    DIAGNOSE("Clinical", Icons.Default.Biotech, "nav_diagnose"),
    HMEM("H-MEM", Icons.Default.Storage, "nav_hmem"),
    ZETARIS("Zetaris", Icons.Default.Dataset, "nav_zetaris"),
    CODE_HUB("Code Hub", Icons.Default.Code, "nav_code_hub"),
    SETTINGS("Settings", Icons.Default.Settings, "nav_settings")
}

class MainActivity : ComponentActivity() {
    private val viewModel: MainViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MyApplicationTheme {
                MainApp(viewModel = viewModel)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainApp(viewModel: MainViewModel) {
    var currentScreen by remember { mutableStateOf(NavDestination.DIAGNOSE) }

    // Predictive back handler: if on sub-screens, navigate back to Diagnose
    if (currentScreen != NavDestination.DIAGNOSE) {
        BackHandler {
            currentScreen = NavDestination.DIAGNOSE
        }
    }

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        // Cameroon flag badge dots (Green, Red with yellow star, Yellow)
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier
                                .clip(RoundedCornerShape(4.dp))
                                .background(Color(0xFFE8F5E9))
                                .padding(horizontal = 6.dp, vertical = 3.dp)
                        ) {
                            Box(modifier = Modifier.size(7.dp).clip(CircleShape).background(Color(0xFF007A3D)))
                            Spacer(modifier = Modifier.width(3.dp))
                            Box(modifier = Modifier.size(7.dp).clip(CircleShape).background(Color(0xFFCE1126)))
                            Spacer(modifier = Modifier.width(3.dp))
                            Box(modifier = Modifier.size(7.dp).clip(CircleShape).background(Color(0xFFFCD116)))
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = "CAMEROON",
                                fontSize = 10.sp,
                                fontWeight = FontWeight.Black,
                                color = Color(0xFF004D26)
                            )
                        }

                        Spacer(modifier = Modifier.width(10.dp))

                        Column {
                            Text(
                                text = "Malaria Agent",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Zetaris + Nightshift Nemotron",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                },
                actions = {
                    AssistChip(
                        onClick = { currentScreen = NavDestination.SETTINGS },
                        label = {
                            Text(
                                text = "H-MEM Live",
                                fontSize = 10.sp,
                                fontWeight = FontWeight.Bold
                            )
                        },
                        leadingIcon = {
                            Box(
                                modifier = Modifier
                                    .size(8.dp)
                                    .clip(CircleShape)
                                    .background(Color(0xFF2E7D32))
                            )
                        },
                        modifier = Modifier
                            .padding(end = 12.dp)
                            .testTag("status_chip")
                    )
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
        },
        bottomBar = {
            NavigationBar(
                modifier = Modifier.testTag("bottom_nav_bar")
            ) {
                NavDestination.entries.forEach { destination ->
                    val isSelected = currentScreen == destination
                    NavigationBarItem(
                        selected = isSelected,
                        onClick = { currentScreen = destination },
                        icon = {
                            Icon(
                                imageVector = destination.icon,
                                contentDescription = destination.label
                            )
                        },
                        label = {
                            Text(
                                text = destination.label,
                                fontSize = 11.sp,
                                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal
                            )
                        },
                        modifier = Modifier.testTag(destination.tag)
                    )
                }
            }
        }
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
        ) {
            when (currentScreen) {
                NavDestination.DIAGNOSE -> DiagnoseScreen(viewModel = viewModel)
                NavDestination.HMEM -> HMemScreen(viewModel = viewModel)
                NavDestination.ZETARIS -> ZetarisScreen(viewModel = viewModel)
                NavDestination.CODE_HUB -> CodeHubScreen()
                NavDestination.SETTINGS -> SettingsScreen(viewModel = viewModel)
            }
        }
    }
}
