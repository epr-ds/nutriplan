package com.nutriplan.android.di

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import org.koin.core.context.GlobalContext

/**
 * Resolve [T] from the global Koin instance started by `KoinInitializer`.
 */
@Composable
inline fun <reified T : Any> koinInject(): T = remember { GlobalContext.get().get<T>() }
