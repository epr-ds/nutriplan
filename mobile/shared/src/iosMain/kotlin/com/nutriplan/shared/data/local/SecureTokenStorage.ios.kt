package com.nutriplan.shared.data.local

import kotlinx.cinterop.BetaInteropApi
import kotlinx.cinterop.ExperimentalForeignApi
import kotlinx.cinterop.alloc
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.ptr
import kotlinx.cinterop.value
import platform.CoreFoundation.CFDictionaryAddValue
import platform.CoreFoundation.CFDictionaryCreateMutable
import platform.CoreFoundation.CFMutableDictionaryRef
import platform.CoreFoundation.CFRelease
import platform.CoreFoundation.CFStringRef
import platform.CoreFoundation.CFTypeRefVar
import platform.CoreFoundation.kCFBooleanTrue
import platform.CoreFoundation.kCFTypeDictionaryKeyCallBacks
import platform.CoreFoundation.kCFTypeDictionaryValueCallBacks
import platform.Foundation.CFBridgingRelease
import platform.Foundation.CFBridgingRetain
import platform.Foundation.NSData
import platform.Foundation.NSString
import platform.Foundation.NSUTF8StringEncoding
import platform.Foundation.create
import platform.Foundation.dataUsingEncoding
import platform.Security.SecItemAdd
import platform.Security.SecItemCopyMatching
import platform.Security.SecItemDelete
import platform.Security.errSecSuccess
import platform.Security.kSecAttrAccessible
import platform.Security.kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
import platform.Security.kSecAttrAccount
import platform.Security.kSecAttrService
import platform.Security.kSecClass
import platform.Security.kSecClassGenericPassword
import platform.Security.kSecMatchLimit
import platform.Security.kSecMatchLimitOne
import platform.Security.kSecReturnData
import platform.Security.kSecValueData

@OptIn(ExperimentalForeignApi::class, BetaInteropApi::class)
actual class SecureTokenStorage : TokenStorage {

    actual override fun load(): StoredTokens? {
        val access = read(ACCESS_ACCOUNT) ?: return null
        val refresh = read(REFRESH_ACCOUNT) ?: return null
        return StoredTokens(access, refresh)
    }

    actual override fun save(accessToken: String, refreshToken: String) {
        write(ACCESS_ACCOUNT, accessToken)
        write(REFRESH_ACCOUNT, refreshToken)
    }

    actual override fun clear() {
        delete(ACCESS_ACCOUNT)
        delete(REFRESH_ACCOUNT)
    }

    private fun read(account: String): String? = memScoped {
        val query = newQuery(account)
        CFDictionaryAddValue(query, kSecReturnData, kCFBooleanTrue)
        CFDictionaryAddValue(query, kSecMatchLimit, kSecMatchLimitOne)

        val result = alloc<CFTypeRefVar>()
        val status = SecItemCopyMatching(query, result.ptr)
        CFRelease(query)
        if (status != errSecSuccess) return@memScoped null

        val data = CFBridgingRelease(result.value) as? NSData ?: return@memScoped null
        NSString.create(data = data, encoding = NSUTF8StringEncoding) as String?
    }

    private fun write(account: String, value: String) {
        delete(account)
        val data = NSString.create(string = value).dataUsingEncoding(NSUTF8StringEncoding) ?: return

        val query = newQuery(account)
        query.put(kSecValueData, data)
        CFDictionaryAddValue(query, kSecAttrAccessible, kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly)
        SecItemAdd(query, null)
        CFRelease(query)
    }

    private fun delete(account: String) {
        val query = newQuery(account)
        SecItemDelete(query)
        CFRelease(query)
    }

    /** A generic-password query scoped to this app's service and the given account. */
    private fun newQuery(account: String): CFMutableDictionaryRef? {
        val query = CFDictionaryCreateMutable(
            null,
            0,
            kCFTypeDictionaryKeyCallBacks.ptr,
            kCFTypeDictionaryValueCallBacks.ptr,
        )
        CFDictionaryAddValue(query, kSecClass, kSecClassGenericPassword)
        query.put(kSecAttrService, SERVICE)
        query.put(kSecAttrAccount, account)
        return query
    }

    /** Add an Objective-C/Kotlin value; the dictionary retains it, so release our extra reference. */
    private fun CFMutableDictionaryRef?.put(key: CFStringRef?, value: Any) {
        val ref = CFBridgingRetain(value)
        CFDictionaryAddValue(this, key, ref)
        CFRelease(ref)
    }

    private companion object {
        const val SERVICE = "com.nutriplan.session"
        const val ACCESS_ACCOUNT = "access_token"
        const val REFRESH_ACCOUNT = "refresh_token"
    }
}
