package com.nutriplan.shared.data.model

import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** The recipe models against payloads shaped like `contracts/dietary.openapi.yaml`. */
class RecipeModelsTest {

    /** Same settings as the app's HTTP client. */
    private val json = Json {
        isLenient = true
        ignoreUnknownKeys = true
        prettyPrint = false
        encodeDefaults = true
    }

    @Test
    fun `search query has the contract's paging defaults`() {
        val query = RecipeSearchQuery()

        assertEquals(emptyList(), query.ingredients)
        assertNull(query.dietType)
        assertNull(query.maxCalories)
        assertNull(query.minProtein)
        assertEquals(1, query.page)
        assertEquals(20, query.limit)
    }

    @Test
    fun `decodes a full recipe`() {
        val recipe = json.decodeFromString<Recipe>(FULL_RECIPE)

        assertEquals("lentil-soup", recipe.id)
        assertEquals("Lentil soup", recipe.name)
        assertEquals("Warm and filling", recipe.description)
        assertEquals(4, recipe.servings)
        assertEquals(10, recipe.prepTime)
        assertEquals(30, recipe.cookTime)
        assertEquals("https://example.com/soup.jpg", recipe.imageUrl)
        assertEquals(listOf("vegan", "vegetarian"), recipe.dietaryTypes)
        assertEquals(listOf("Chop the onion", "Simmer the lentils"), recipe.instructions)
        assertEquals(320, recipe.nutritionalInfo?.calories)
        assertEquals(18.5, recipe.nutritionalInfo?.protein)
    }

    @Test
    fun `decodes ingredients, keeping unknown quantities as null rather than zero`() {
        val ingredients = json.decodeFromString<Recipe>(FULL_RECIPE).ingredients

        assertEquals(2, ingredients.size)
        assertEquals(RecipeIngredient(name = "lentils", quantity = 200.0, unit = "g", calories = 230, protein = 18.0), ingredients[0])
        assertEquals(RecipeIngredient(name = "salt"), ingredients[1])
        assertNull(ingredients[1].quantity)
    }

    @Test
    fun `a recipe with only the required fields still decodes`() {
        val recipe = json.decodeFromString<Recipe>("""{"id":"r1","name":"Toast"}""")

        assertEquals(emptyList(), recipe.ingredients)
        assertEquals(emptyList(), recipe.instructions)
        assertEquals(emptyList(), recipe.dietaryTypes)
        assertNull(recipe.nutritionalInfo)
        assertNull(recipe.servings)
    }

    @Test
    fun `explicit nulls from the server are accepted`() {
        val recipe = json.decodeFromString<Recipe>(
            """{"id":"r1","name":"Toast","description":null,"prepTime":null,"cookTime":null,"servings":null,"imageUrl":null,"nutritionalInfo":null}""",
        )

        assertNull(recipe.description)
        assertNull(recipe.imageUrl)
    }

    @Test
    fun `decodes a page of search results`() {
        val recipes = json.decodeFromString<List<Recipe>>("[$FULL_RECIPE, {\"id\":\"r2\",\"name\":\"Toast\"}]")

        assertEquals(listOf("lentil-soup", "r2"), recipes.map { it.id })
    }

    @Test
    fun `decodes the nutrition disclaimer with its sources`() {
        val disclaimer = json.decodeFromString<NutritionDisclaimer>(
            """
            {
              "disclaimer":"Values are estimates and not medical advice.",
              "medicalAdvice":false,
              "sources":[{"id":"usda","name":"USDA FoodData Central","url":"https://fdc.nal.usda.gov","verified":true}],
              "fieldSources":{"calories":"usda","protein":"usda","carbs":"usda","fat":"usda","sugar":"usda"},
              "lastReviewed":"2026-09-01"
            }
            """,
        )

        assertEquals("Values are estimates and not medical advice.", disclaimer.disclaimer)
        assertFalse(disclaimer.medicalAdvice)
        assertEquals("USDA FoodData Central", disclaimer.sources.single().name)
        assertTrue(disclaimer.sources.single().verified)
        assertEquals("2026-09-01", disclaimer.lastReviewed)
    }

    private companion object {
        val FULL_RECIPE = """
            {
              "id":"lentil-soup","name":"Lentil soup","description":"Warm and filling",
              "ingredients":[
                {"name":"lentils","quantity":200.0,"unit":"g","calories":230,"protein":18.0},
                {"name":"salt"}
              ],
              "instructions":["Chop the onion","Simmer the lentils"],
              "prepTime":10,"cookTime":30,"servings":4,
              "imageUrl":"https://example.com/soup.jpg",
              "nutritionalInfo":{"calories":320,"protein":18.5,"carbs":45.0,"fat":6.0,"sugar":5.0},
              "dietaryTypes":["vegan","vegetarian"]
            }
        """.trimIndent()
    }
}
