package com.nutriplan.android.screen.checkout

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import com.nutriplan.android.component.NutriPlanButton
import com.nutriplan.shared.ui.theme.NutriPlanTheme
import org.koin.androidx.compose.koinInject

/**
 * Checkout screen for ordering meal plans.
 */
@Composable
fun CheckoutScreen(
    planId: String,
    onCheckoutSuccess: () -> Unit,
    onNavigateBack: () -> Unit
) {
    val commerceRepository = koinInject<com.nutriplan.shared.repository.CommerceRepository>()
    
    var mealPlan by remember { mutableStateOf<com.nutriplan.shared.model.MealPlan?>(null) }
    var cartItems by remember { mutableStateOf<List<com.nutriplan.shared.model.CartItem>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var isProcessing by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(planId) {
        // TODO: Load meal plan and cart items
        // mealPlan = commerceRepository.getMealPlan(planId)
        // cartItems = commerceRepository.getCartItems()
        isLoading = false
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Checkout") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            Icons.Default.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                }
            )
        }
    ) { paddingValues ->
        if (isLoading) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Order summary
                item {
                    Text(
                        text = "Order Summary",
                        style = MaterialTheme.typography.titleLarge,
                        color = NutriPlanTheme.colors.onSurface
                    )
                    
                    Spacer(modifier = Modifier.height(8.dp))
                }
                
                // Cart items
                items(cartItems, key = { it.id }) { item ->
                    CartItemRow(cartItem = item)
                }
                
                item {
                    Spacer(modifier = Modifier.height(16.dp))
                    
                    Divider()
                    
                    Spacer(modifier = Modifier.height(16.dp))
                    
                    // Price breakdown
                    PriceRow(label = "Subtotal", price = "$100.00")
                    PriceRow(label = "Tax", price = "$8.00")
                    PriceRow(
                        label = "Total",
                        price = "$108.00",
                        isTotal = true
                    )
                }
                
                item {
                    Spacer(modifier = Modifier.height(24.dp))
                    
                    // Payment method
                    Text(
                        text = "Payment Method",
                        style = MaterialTheme.typography.titleMedium,
                        color = NutriPlanTheme.colors.onSurface
                    )
                    
                    Spacer(modifier = Modifier.height(8.dp))
                    
                    Card(
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(16.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(
                                    Icons.Default.CreditCard,
                                    contentDescription = "Credit Card",
                                    tint = NutriPlanTheme.colors.primary
                                )
                                Text(
                                    text = "•••• •••• •••• 4242",
                                    style = MaterialTheme.typography.bodyMedium
                                )
                            }
                            
                            TextButton(onClick = { /* TODO: Change payment method */ }) {
                                Text("Change")
                            }
                        }
                    }
                    
                    Spacer(modifier = Modifier.height(24.dp))
                    
                    // Place order button
                    NutriPlanButton(
                        onClick = {
                            isProcessing = true
                            errorMessage = null
                            // TODO: Process checkout
                            // commerceRepository.checkout(planId, cartItems)
                            isProcessing = false
                            onCheckoutSuccess()
                        },
                        isLoading = isProcessing,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("Place Order - $108.00")
                    }
                    
                    Spacer(modifier = Modifier.height(16.dp))
                    
                    // Terms and conditions
                    Text(
                        text = "By placing your order, you agree to our Terms and Conditions.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                        textDecoration = TextDecoration.Underline
                    )
                }
            }
        }
    }
}

/**
 * Cart item row component.
 */
@Composable
fun CartItemRow(
    cartItem: com.nutriplan.shared.model.CartItem
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column {
            Text(
                text = cartItem.name,
                style = MaterialTheme.typography.bodyMedium,
                color = NutriPlanTheme.colors.onSurface
            )
            Text(
                text = "${cartItem.quantity}x $${cartItem.unitPrice}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
            )
        }
        
        Text(
            text = "$${String.format("%.2f", cartItem.subtotal)}",
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
        )
    }
}

/**
 * Price row component.
 */
@Composable
fun PriceRow(
    label: String,
    price: String,
    isTotal: Boolean = false
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = if (isTotal) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyMedium,
            fontWeight = if (isTotal) androidx.compose.ui.text.font.FontWeight.Bold else androidx.compose.ui.text.font.FontWeight.Normal,
            color = if (isTotal) NutriPlanTheme.colors.onSurface else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
        )
        
        Text(
            text = price,
            style = if (isTotal) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyMedium,
            fontWeight = if (isTotal) androidx.compose.ui.text.font.FontWeight.Bold else androidx.compose.ui.text.font.FontWeight.Normal,
            color = if (isTotal) NutriPlanTheme.colors.primary else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f)
        )
    }
}
