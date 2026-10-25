package com.example.data

import com.example.data.models.ClinicalVisit
import com.example.data.models.EpidemiologyZone
import com.example.data.models.Patient

object SyntheticDataProvider {

    val patients = listOf(
        Patient(
            patientId = "123",
            name = "Ndongho Emmanuel",
            village = "Buea",
            familyHistory = true,
            age = 28,
            gender = "Male",
            phone = "+237 671-88-29-10"
        ),
        Patient(
            patientId = "p101-buea-482a-991f",
            name = "Mbah Beatrice",
            village = "Buea",
            familyHistory = true,
            age = 34,
            gender = "Female",
            phone = "+237 677-24-11-90"
        ),
        Patient(
            patientId = "p102-limbe-781c-432d",
            name = "Ewodo Joseph",
            village = "Limbe",
            familyHistory = false,
            age = 42,
            gender = "Male",
            phone = "+237 699-12-88-34"
        ),
        Patient(
            patientId = "p103-douala-319a-554e",
            name = "Kamgaing Samuel",
            village = "Douala",
            familyHistory = true,
            age = 19,
            gender = "Male",
            phone = "+237 655-40-22-18"
        ),
        Patient(
            patientId = "p104-yaounde-902b-118c",
            name = "Onana Stephanie",
            village = "Yaoundé",
            familyHistory = false,
            age = 26,
            gender = "Female",
            phone = "+237 672-01-99-44"
        ),
        Patient(
            patientId = "p105-bamenda-643d-771a",
            name = "Fru Collins",
            village = "Bamenda",
            familyHistory = true,
            age = 51,
            gender = "Male",
            phone = "+237 674-88-33-01"
        ),
        Patient(
            patientId = "p106-kumba-821f-223b",
            name = "Enow Comfort",
            village = "Kumba",
            familyHistory = true,
            age = 23,
            gender = "Female",
            phone = "+237 679-55-12-07"
        )
    )

    val clinicalVisits = listOf(
        ClinicalVisit("v801-91a3-44b2", "p101-buea-482a-991f", 39.4f, true, "2026-10-21"),
        ClinicalVisit("v802-12c8-87d1", "p102-limbe-781c-432d", 38.8f, true, "2026-10-22"),
        ClinicalVisit("v803-55f4-33a9", "p103-douala-319a-554e", 37.2f, false, "2026-10-23"),
        ClinicalVisit("v804-77e2-19c4", "p104-yaounde-902b-118c", 38.9f, true, "2026-10-24"),
        ClinicalVisit("v805-33d1-66e8", "p105-bamenda-643d-771a", 39.7f, true, "2026-10-24"),
        ClinicalVisit("v806-99a4-55c3", "p106-kumba-821f-223b", 39.1f, true, "2026-10-25"),
        ClinicalVisit("v807-demo-0123", "123", 39.4f, true, "2026-10-25")
    )

    val regionalEpidemiology = listOf(
        EpidemiologyZone("Buea", "Southwest Region", "High", 42, "High vector density (foothills of Mt Cameroon)"),
        EpidemiologyZone("Limbe", "Southwest Region", "High", 38, "Coastal high humidity; elevated breeding sites"),
        EpidemiologyZone("Douala", "Littoral Region", "Medium", 29, "Urban peri-marshlands transmission"),
        EpidemiologyZone("Yaoundé", "Centre Region", "Medium", 21, "Plateau urban & peri-urban pockets"),
        EpidemiologyZone("Bamenda", "Northwest Region", "Low", 14, "High altitude highland temperate climate"),
        EpidemiologyZone("Kumba", "Southwest Region", "High", 47, "Dense tropical rainforest endemic basin")
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
                            "family_history" to p.familyHistory.toString(),
                            "endemic_zone" to (epi?.endemicZone ?: "Unknown"),
                            "active_cases" to (epi?.activeCases?.toString() ?: "0")
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
                                "region" to e.region,
                                "endemic_zone" to e.endemicZone,
                                "active_cases" to e.activeCases.toString(),
                                "vector_risk" to e.vectorRisk
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
                            "fever_temp" to "${v.feverTemp}°C",
                            "body_pain" to v.bodyPain.toString(),
                            "date" to v.date
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
                            "name" to p.name,
                            "village" to p.village,
                            "family_history" to p.familyHistory.toString(),
                            "age" to p.age.toString(),
                            "gender" to p.gender
                        )
                    )
                }
            }
        }
        return results
    }
}
