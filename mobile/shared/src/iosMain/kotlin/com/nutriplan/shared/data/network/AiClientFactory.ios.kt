package com.nutriplan.shared.data.network

import io.ktor.client.HttpClient
import io.ktor.client.engine.darwin.Darwin

internal actual fun createAiClient(): HttpClient = HttpClientFactory.create(Darwin.create(), authRepository = null)