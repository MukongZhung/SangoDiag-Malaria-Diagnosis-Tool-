package com.example

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.example.data.SyntheticDataProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class ExampleRobolectricTest {

  @Test
  fun `read string from context`() {
    val context = ApplicationProvider.getApplicationContext<Context>()
    val appName = context.getString(R.string.app_name)
    assertEquals("Malaria Agent", appName)
  }

  @Test
  fun `verify synthetic data provider patients and epidemiology`() {
    val patients = SyntheticDataProvider.patients
    assertTrue(patients.isNotEmpty())
    val patient123 = patients.find { it.patientId == "123" }
    assertNotNull(patient123)
    assertEquals("Buea", patient123?.village)

    val queryResult = SyntheticDataProvider.executeFederatedSql(
      "SELECT * FROM regional_epidemiology WHERE endemic_zone = 'High';"
    )
    assertTrue(queryResult.isNotEmpty())
  }
}
