package com.nutriplan.android.screen.recipes

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material3.Icon
import androidx.compose.material3.IconToggleButton
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.material3.Text
import com.nutriplan.android.R
import com.nutriplan.android.i18n.changeMessageRes
import com.nutriplan.shared.recipes.FavoriteError

/** Test tags shared by the places that show a favorite heart (used by the Robolectric UI tests). */
object FavoriteTestTags {
    const val TOGGLE = "favorite_toggle"
    const val ERROR_BANNER = "favorite_error_banner"
}

/**
 * What a recipe's heart shows and does (DPL-607): [isFavorite] is the current state, [enabled] is
 * false while the change is being sent, and [onToggle] flips it.
 */
internal class FavoriteAction(
    val isFavorite: Boolean,
    val enabled: Boolean,
    val onToggle: () -> Unit,
)

/**
 * The heart that saves a recipe as a favorite or takes it back. The label says what a tap does
 * ("Save to favorites" / "Remove from favorites"), and the filled heart is not the only signal: the
 * button is a toggle, so a screen reader also announces whether it is on.
 */
@Composable
internal fun FavoriteButton(action: FavoriteAction, modifier: Modifier = Modifier) {
    IconToggleButton(
        checked = action.isFavorite,
        onCheckedChange = { action.onToggle() },
        enabled = action.enabled,
        modifier = modifier.testTag(FavoriteTestTags.TOGGLE),
    ) {
        Icon(
            imageVector = if (action.isFavorite) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
            contentDescription = stringResource(
                if (action.isFavorite) R.string.favorite_remove else R.string.favorite_add,
            ),
            tint = if (action.isFavorite) MaterialTheme.colorScheme.primary else LocalContentColor.current,
        )
    }
}

/** The message about a heart that was put back because its change failed. Announced politely. */
@Composable
internal fun FavoriteChangeError(error: FavoriteError, modifier: Modifier = Modifier) {
    Text(
        text = stringResource(error.changeMessageRes()),
        color = MaterialTheme.colorScheme.error,
        style = MaterialTheme.typography.bodyMedium,
        modifier = modifier
            .testTag(FavoriteTestTags.ERROR_BANNER)
            .semantics { liveRegion = LiveRegionMode.Polite },
    )
}
