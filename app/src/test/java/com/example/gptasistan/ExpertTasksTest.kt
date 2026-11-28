package com.example.gptasistan

import org.junit.Assert.*
import org.junit.Test

class ExpertTasksTest {
    @Test fun statusBatchUsesOnlyTwoCachedReadsWithoutHistoryOrMemory() {
        val jobs = ExpertTasks.statusBatch()
        assertEquals(2, jobs.length())
        assertEquals(listOf("status", "models.cached"),
            (0 until jobs.length()).map { jobs.getJSONObject(it).getString("kind") })
        assertTrue(OwnerGateway.workerTaskDigest(jobs).matches(Regex("[a-f0-9]{64}")))
    }

    @Test fun onlyExactServerTaskIdsAreAccepted() {
        assertTrue(ExpertTasks.validTaskId("a".repeat(32)))
        listOf("A".repeat(32), "a".repeat(31), "a".repeat(32) + "\n", "https://server.example/task")
            .forEach { assertFalse(ExpertTasks.validTaskId(it)) }
    }
}
