package com.nutriplan.shared.data.model

import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** COM-501: the Commerce models read and write exactly the shapes of `contracts/commerce.openapi.yaml`. */
class CommerceModelsTest {

    /** The same settings as the app's HTTP client. */
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
        isLenient = true
    }

    private fun keys(value: String) = json.parseToJsonElement(value).jsonObject.keys

    private val address = OrderAddress(
        street = "Av. Reforma 222",
        city = "Ciudad de México",
        state = "CDMX",
        zipCode = "06600",
        country = "MX",
    )

    // --- requests ---

    @Test
    fun `a minimal order request sends only the required fields`() {
        val body = json.encodeToString(
            CreateOrderRequest.serializer(),
            CreateOrderRequest(
                mealPlanId = "p1",
                fulfillmentType = "dark_kitchen",
                deliveryAddress = address,
                deliveryDate = "2026-11-02",
                deliveryTimeSlot = "13:00-14:00",
            ),
        )

        assertEquals(setOf("mealPlanId", "fulfillmentType", "deliveryAddress", "deliveryDate", "deliveryTimeSlot"), keys(body))
        assertEquals(
            setOf("street", "city", "state", "zipCode", "country"),
            json.parseToJsonElement(body).jsonObject.getValue("deliveryAddress").jsonObject.keys,
        )
    }

    @Test
    fun `a full order request uses only documented fields`() {
        val body = json.encodeToString(
            CreateOrderRequest.serializer(),
            CreateOrderRequest(
                mealPlanId = "p1",
                fulfillmentType = "grocery_delivery",
                providerId = "freshbasket",
                deliveryAddress = address.copy(apartment = "4B", instructions = "Ring twice"),
                deliveryDate = "2026-11-02",
                deliveryTimeSlot = "13:00-14:00",
                paymentMethod = PaymentMethodRequest(type = "oxxo", token = "tok_1"),
                notes = "No plastic bags",
            ),
        )

        assertEquals(
            setOf(
                "mealPlanId",
                "fulfillmentType",
                "providerId",
                "deliveryAddress",
                "deliveryDate",
                "deliveryTimeSlot",
                "paymentMethod",
                "notes",
            ),
            keys(body),
        )
        assertTrue(""""paymentMethod":{"type":"oxxo","token":"tok_1"}""" in body)
        assertTrue(""""apartment":"4B"""" in body)
    }

    @Test
    fun `a cancel request without a refund amount is an empty object`() {
        assertEquals("{}", json.encodeToString(CancelOrderRequest.serializer(), CancelOrderRequest()))
        assertEquals(
            """{"refundAmount":120.5}""",
            json.encodeToString(CancelOrderRequest.serializer(), CancelOrderRequest(refundAmount = 120.5)),
        )
    }

    @Test
    fun `saving a wallet sends only its type and token`() {
        assertEquals(
            """{"type":"paypal","token":"tok_pp"}""",
            json.encodeToString(SavePaymentMethodRequest.serializer(), SavePaymentMethodRequest("paypal", "tok_pp")),
        )
    }

    @Test
    fun `saving a card sends its display metadata`() {
        val body = json.encodeToString(
            SavePaymentMethodRequest.serializer(),
            SavePaymentMethodRequest("credit_card", "tok_c", brand = "visa", last4 = "4242", expMonth = 12, expYear = 2030),
        )

        assertEquals(setOf("type", "token", "brand", "last4", "expMonth", "expYear"), keys(body))
    }

    @Test
    fun `a grocery search sends its items and zip code`() {
        assertEquals(
            """{"items":[{"ingredient":"rice","quantity":500.0,"unit":"g"}],"zipCode":"06600"}""",
            json.encodeToString(
                GrocerySearchRequest.serializer(),
                GrocerySearchRequest(items = listOf(GrocerySearchItem("rice", 500.0, "g")), zipCode = "06600"),
            ),
        )
    }

    // --- responses ---

    @Test
    fun `an order decodes its money lines and payment instructions`() {
        val order = json.decodeFromString(
            Order.serializer(),
            """
            {"id":"o1","status":"pending","fulfillmentType":"dark_kitchen",
             "provider":{"id":"k1","name":"Cocina Roma","type":"dark_kitchen"},
             "items":[{"name":"Lentil soup","quantity":2,"unit":"portion",
               "unitPrice":{"amount":89.0,"currency":"MXN","formatted":"${'$'}89.00"},
               "lineTotal":{"amount":178.0,"currency":"MXN","formatted":"${'$'}178.00"}}],
             "subtotal":{"amount":178.0,"currency":"MXN","formatted":"${'$'}178.00"},
             "deliveryFee":{"amount":30.0},
             "total":{"amount":208.0,"currency":"MXN","formatted":"${'$'}208.00"},
             "estimatedDelivery":"2026-11-02T13:30:00Z",
             "voucher":{"reference":"9300 1234","amount":{"amount":208.0},"expiresAt":"2026-11-01T23:59:00Z",
               "provider":"conekta","barcodeUrl":"https://pay.example/b.png"}}
            """.trimIndent(),
        )

        assertEquals("pending", order.status)
        assertEquals("Cocina Roma", order.provider?.name)
        assertEquals(2.0, order.items.single().quantity)
        assertEquals("${'$'}178.00", order.items.single().lineTotal?.formatted)
        assertEquals(208.0, order.total?.amount)
        // The currency defaults to MXN when the server leaves it out.
        assertEquals("MXN", order.deliveryFee?.currency)
        assertEquals("9300 1234", order.voucher?.reference)
        assertNull(order.transfer)
        assertNull(order.refund)
    }

    @Test
    fun `an order decodes with only its id`() {
        val order = json.decodeFromString(Order.serializer(), """{"id":"o1"}""")

        assertTrue(order.items.isEmpty())
        assertNull(order.status)
        assertNull(order.total)
    }

    @Test
    fun `a cancelled grocery order decodes its refund and grocery order`() {
        val order = json.decodeFromString(
            Order.serializer(),
            """{"id":"o2","status":"cancelled","fulfillmentType":"grocery_delivery",
               "refund":{"refundId":"re_1","status":"partial","amount":{"amount":50.0},"provider":"stripe"},
               "groceryOrder":{"providerId":"freshbasket","externalOrderId":"FB-77","status":"out_for_delivery"},
               "transfer":{"clabe":"646180157000000004","reference":"REF1"},
               "approval":{"approvalUrl":"https://paypal.example/a","reference":"PP-1"}}""",
        )

        assertEquals("partial", order.refund?.status)
        assertEquals("out_for_delivery", order.groceryOrder?.status)
        assertEquals("646180157000000004", order.transfer?.clabe)
        assertEquals("https://paypal.example/a", order.approval?.approvalUrl)
    }

    @Test
    fun `saved payment methods decode without any token`() {
        val methods = json.decodeFromString(
            ListSerializer(PaymentMethod.serializer()),
            """[{"id":"pm1","type":"credit_card","brand":"visa","last4":"4242","expMonth":12,"expYear":2030,
                 "createdAt":"2026-10-01T10:00:00Z"},{"id":"pm2","type":"paypal"}]""",
        )

        assertEquals("4242", methods.first().last4)
        assertNull(methods.last().last4)
    }

    @Test
    fun `kitchen availability and providers decode`() {
        val availability = json.decodeFromString(
            KitchenAvailability.serializer(),
            """{"available":true,"zipCode":"06600","timeSlots":["13:00-14:00","19:00-20:00"]}""",
        )
        val providers = json.decodeFromString(
            ListSerializer(FulfillmentProvider.serializer()),
            """[{"id":"freshbasket","name":"FreshBasket","type":"grocery","logoUrl":"https://cdn.example/fb.png",""" +
                """"estimatedDelivery":"2h"}]""",
        )

        assertTrue(availability.available)
        assertEquals(2, availability.timeSlots.size)
        assertEquals("grocery", providers.single().type)
        assertEquals(false, json.decodeFromString(KitchenAvailability.serializer(), "{}").available)
    }
}
