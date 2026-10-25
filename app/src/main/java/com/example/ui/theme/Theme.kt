package com.example.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext

private val DarkColorScheme = darkColorScheme(
    primary = MedicalGreenPrimaryDark,
    onPrimary = MedicalGreenOnPrimaryDark,
    primaryContainer = MedicalGreenPrimaryContainerDark,
    onPrimaryContainer = MedicalGreenOnPrimaryContainerDark,
    secondary = OchreSecondaryDark,
    onSecondary = OchreOnSecondaryDark,
    secondaryContainer = OchreSecondaryContainerDark,
    onSecondaryContainer = OchreOnSecondaryContainerDark,
    tertiary = AlertRedTertiaryDark,
    tertiaryContainer = AlertRedTertiaryContainerDark,
    onTertiaryContainer = AlertRedOnTertiaryContainerDark,
    background = BackgroundDark,
    surface = SurfaceDark,
    surfaceVariant = SurfaceVariantDark,
    outline = OutlineDark
)

private val LightColorScheme = lightColorScheme(
    primary = MedicalGreenPrimary,
    onPrimary = MedicalGreenOnPrimary,
    primaryContainer = MedicalGreenPrimaryContainer,
    onPrimaryContainer = MedicalGreenOnPrimaryContainer,
    secondary = OchreSecondary,
    onSecondary = OchreOnSecondary,
    secondaryContainer = OchreSecondaryContainer,
    onSecondaryContainer = OchreOnSecondaryContainer,
    tertiary = AlertRedTertiary,
    tertiaryContainer = AlertRedTertiaryContainer,
    onTertiaryContainer = AlertRedOnTertiaryContainer,
    background = BackgroundLight,
    surface = SurfaceLight,
    surfaceVariant = SurfaceVariantLight,
    outline = OutlineLight
)

@Composable
fun MyApplicationTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = false, // Use our tailored clinical palette by default
    content: @Composable () -> Unit
) {
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColorScheme
        else -> LightColorScheme
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}
