package com.nutriplan.shared.data.network

import io.ktor.client.HttpClient
import io.ktor.client.engine.okhttp.OkHttp

internal actual fun createAiClient(): HttpClient = HttpClientFactory.create(OkHttp.create(), authRepository = null)