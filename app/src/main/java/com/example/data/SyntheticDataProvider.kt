package com.example.data

import com.example.data.models.ClinicalVisit
import com.example.data.models.EpidemiologyZone
import com.example.data.models.Patient

// Mirrors synthetic_data/*.csv (hackathon dataset). Region names are added for display only.
object SyntheticDataProvider {

    val patients = listOf(
        Patient(
            patientId = "a1c3e5f7-2b4d-4c6e-8f10-1a2b3c4d5e01",
            name = "Patient 01",
            village = "Limbe",
            familyHistory = true,
            age = 34,
            gender = "Female",
            recentTravel = false
        ),
        Patient(
            patientId = "b2d4f6a8-3c5e-4d7f-9a21-2b3c4d5e6f02",
            name = "Patient 02",
            village = "Ebolowa",
            familyHistory = true,
            age = 27,
            gender = "Male",
            recentTravel = true
        ),
        Patient(
            patientId = "c3e5a7b9-4d6f-4e8a-a132-3c4d5e6f7a03",
            name = "Patient 03",
            village = "Kribi",
            familyHistory = false,
            age = 6,
            gender = "Female",
            recentTravel = false
        ),
        Patient(
            patientId = "d4f6b8c0-5e7a-4f9b-b243-4d5e6f7a8b04",
            name = "Patient 04",
            village = "Bertoua",
            familyHistory = true,
            age = 52,
            gender = "Male",
            recentTravel = false
        ),
        Patient(
            patientId = "e5a7c9d1-6f8b-4a0c-8354-5e6f7a8b9c05",
            name = "Patient 05",
            village = "Buea",
            familyHistory = false,
            age = 41,
            gender = "Female",
            recentTravel = true
        ),
        Patient(
            patientId = "f6b8d0e2-7a9c-4b1d-9465-6f7a8b9c0d06",
            name = "Patient 06",
            village = "Bafoussam",
            familyHistory = false,
            age = 23,
            gender = "Female",
            recentTravel = false
        ),
        Patient(
            patientId = "a7c9e1f3-8b0d-4c2e-a576-7a8b9c0d1e07",
            name = "Patient 07",
            village = "Dschang",
            familyHistory = false,
            age = 31,
            gender = "Male",
            recentTravel = false
        ),
        Patient(
            patientId = "b8d0f2a4-9c1e-4d3f-b687-8b9c0d1e2f08",
            name = "Patient 08",
            village = "Bamenda",
            familyHistory = false,
            age = 65,
            gender = "Male",
            recentTravel = false
        ),
        Patient(
            patientId = "c9e1a3b5-0d2f-4e4a-8798-9c0d1e2f3a09",
            name = "Patient 09",
            village = "Garoua",
            familyHistory = true,
            age = 3,
            gender = "Male",
            recentTravel = false
        ),
        Patient(
            patientId = "d0f2b4c6-1e3a-4f5b-98a9-0d1e2f3a4b10",
            name = "Patient 10",
            village = "Mbalmayo",
            familyHistory = false,
            age = 19,
            gender = "Female",
            recentTravel = true
        )
    )

    val clinicalVisits = listOf(
        ClinicalVisit("11a2b3c4-d5e6-4f70-8a1b-c2d3e4f5a601", "a1c3e5f7-2b4d-4c6e-8f10-1a2b3c4d5e01", 38.6f, true, true, false, "2026-10-19"),
        ClinicalVisit("22b3c4d5-e6f7-4a81-9b2c-d3e4f5a6b702", "b2d4f6a8-3c5e-4d7f-9a21-2b3c4d5e6f02", 39.8f, true, true, true, "2026-10-20"),
        ClinicalVisit("33c4d5e6-f7a8-4b92-ac3d-e4f5a6b7c803", "c3e5a7b9-4d6f-4e8a-a132-3c4d5e6f7a03", 39.4f, false, true, true, "2026-10-20"),
        ClinicalVisit("44d5e6f7-a8b9-4ca3-bd4e-f5a6b7c8d904", "d4f6b8c0-5e7a-4f9b-b243-4d5e6f7a8b04", null, true, false, false, "2026-10-21"),
        ClinicalVisit("55e6f7a8-b9c0-4db4-8e5f-a6b7c8d9e005", "e5a7c9d1-6f8b-4a0c-8354-5e6f7a8b9c05", 38.2f, false, true, false, "2026-10-21"),
        ClinicalVisit("66f7a8b9-c0d1-4ec5-9f6a-b7c8d9e0f106", "f6b8d0e2-7a9c-4b1d-9465-6f7a8b9c0d06", 37.9f, false, true, false, "2026-10-22"),
        ClinicalVisit("77a8b9c0-d1e2-4fd6-a07b-c8d9e0f1a207", "a7c9e1f3-8b0d-4c2e-a576-7a8b9c0d1e07", 40.1f, true, true, false, "2026-10-22"),
        ClinicalVisit("88b9c0d1-e2f3-40e7-b18c-d9e0f1a2b308", "b8d0f2a4-9c1e-4d3f-b687-8b9c0d1e2f08", null, false, true, false, "2026-10-23"),
        ClinicalVisit("99c0d1e2-f3a4-41f8-829d-e0f1a2b3c409", "c9e1a3b5-0d2f-4e4a-8798-9c0d1e2f3a09", 40.3f, false, false, true, "2026-10-24"),
        ClinicalVisit("aad1e2f3-a4b5-42a9-93ae-f1a2b3c4d510", "d0f2b4c6-1e3a-4f5b-98a9-0d1e2f3a4b10", 38.9f, true, true, true, "2026-10-25")
    )

    val regionalEpidemiology = listOf(
        EpidemiologyZone("Limbe", "Southwest Region", "High", 31, "High"),
        EpidemiologyZone("Ebolowa", "South Region", "High", 44, "High"),
        EpidemiologyZone("Kribi", "South Region", "High", 38, "High"),
        EpidemiologyZone("Bertoua", "East Region", "High", 27, "Medium"),
        EpidemiologyZone("Buea", "Southwest Region", "Medium", 14, "Medium"),
        EpidemiologyZone("Bafoussam", "West Region", "Medium", 11, "Medium"),
        EpidemiologyZone("Dschang", "West Region", "Low", 0, "Low"),
        EpidemiologyZone("Bamenda", "Northwest Region", "Medium", 9, "Medium"),
        EpidemiologyZone("Garoua", "North Region", "High", 35, "Medium"),
        EpidemiologyZone("Mbalmayo", "Centre Region", "High", 29, "High")
    )

    /**
     * Executes federated SQL against synthetic tables simulating Zetaris engine
     */
    fun executeFederatedSql(query: String): List<Map<String, String>> {
        val normalized = query.lowercase().trim()
        val results = mutableListOf<Map<String, String>>()

        when {
            normalized.contains("regional_epidemiology") && normalized.contains("patients") -> {
                // Join query
                for (p in patients) {
                    val epi = regionalEpidemiology.find { it.village.equals(p.village, ignoreCase = true) }
                    results.add(
                        mapOf(
                            "patient_id" to p.patientId,
                            "village" to p.village,
                            "family_history_malaria" to p.familyHistory.toString(),
                            "endemic_zone" to (epi?.endemicZone ?: "Unknown"),
                            "active_cases_this_week" to (epi?.activeCases?.toString() ?: "0")
                        )
                    )
                }
            }
            normalized.contains("from regional_epidemiology") -> {
                val highOnly = normalized.contains("'high'") || normalized.contains("\"high\"")
                for (e in regionalEpidemiology) {
                    if (!highOnly || e.endemicZone.equals("High", ignoreCase = true)) {
                        results.add(
                            mapOf(
                                "village" to e.village,
                                "endemic_zone" to e.endemicZone,
                                "active_cases_this_week" to e.activeCases.toString(),
                                "breeding_site_risk" to e.breedingSiteRisk
                            )
                        )
                    }
                }
            }
            normalized.contains("from clinical_visits") -> {
                for (v in clinicalVisits) {
                    results.add(
                        mapOf(
                            "visit_id" to v.visitId,
                            "patient_id" to v.patientId,
                            "visit_date" to v.date,
                            "fever_temp_c" to (v.feverTemp?.toString() ?: "NULL"),
                            "body_pain" to v.bodyPain.toString(),
                            "headache" to v.headache.toString(),
                            "nausea" to v.nausea.toString()
                        )
                    )
                }
            }
            else -> {
                // Default: select patients
                for (p in patients) {
                    results.add(
                        mapOf(
                            "patient_id" to p.patientId,
                            "age" to p.age.toString(),
                            "gender" to p.gender,
                            "village" to p.village,
                            "family_history_malaria" to p.familyHistory.toString(),
                            "recent_travel" to p.recentTravel.toString()
                        )
                    )
                }
            }
        }
        return results
    }
}
