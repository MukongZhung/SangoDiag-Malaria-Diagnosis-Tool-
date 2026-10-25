package com.example.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "h_mem_patients")
data class HMemEntity(
    @PrimaryKey
    val patientId: String,
    val contextString: String,
    val updatedAt: String,
    val sessionCount: Int
)
