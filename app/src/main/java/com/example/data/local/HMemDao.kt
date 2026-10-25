package com.example.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface HMemDao {
    @Query("SELECT * FROM h_mem_patients WHERE patientId = :patientId LIMIT 1")
    suspend fun getPatientMemory(patientId: String): HMemEntity?

    @Query("SELECT * FROM h_mem_patients ORDER BY updatedAt DESC")
    fun getAllPatientMemories(): Flow<List<HMemEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun savePatientMemory(entity: HMemEntity)

    @Query("DELETE FROM h_mem_patients WHERE patientId = :patientId")
    suspend fun deleteMemory(patientId: String)
}
