package com.nutriplan.android.di

import androidx.compose.runtime.Composable
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import org.koin.core.context.GlobalContext

/** Keeps [value] for as long as the owning screen (its navigation back stack entry) exists. */
class Retained<T : Any>(val value: T) : ViewModel()

/**
 * Resolve [T] from the global Koin instance once per screen: unlike [koinInject], the same
 * instance is returned when the user comes back to the screen from one opened on top of it, so its
 * state (for example an AI answer that cost a request) is not lost.
 */
@Composable
inline fun <reified T : Any> koinInjectRetained(): T =
    viewModel(key = T::class.qualifiedName) { Retained(GlobalContext.get().get<T>()) }.value
