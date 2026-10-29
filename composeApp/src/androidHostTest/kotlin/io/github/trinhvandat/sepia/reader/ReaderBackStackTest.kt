package io.github.trinhvandat.sepia.reader

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ReaderBackStackTest {
    @Test
    fun emptyStackCannotGoBack() {
        val s = ReaderBackStack()
        assertFalse(s.canGoBack)
        assertNull(s.pop())
    }

    @Test
    fun recordThenPopReturnsLastInFirstOut() {
        val s = ReaderBackStack()
        s.recordJump("epubcfi(/6/2!/4)")
        s.recordJump("epubcfi(/6/4!/8)")
        assertTrue(s.canGoBack)
        assertEquals(2, s.size)
        assertEquals("epubcfi(/6/4!/8)", s.pop())
        assertEquals("epubcfi(/6/2!/4)", s.pop())
        assertFalse(s.canGoBack)
    }

    @Test
    fun blankOrNullCfiIsIgnored() {
        val s = ReaderBackStack()
        s.recordJump(null)
        s.recordJump("")
        s.recordJump("   ")
        assertFalse(s.canGoBack)
    }

    @Test
    fun consecutiveDuplicateIsNotPushedTwice() {
        val s = ReaderBackStack()
        s.recordJump("epubcfi(/6/2)")
        s.recordJump("epubcfi(/6/2)")
        assertEquals(1, s.size)
    }

    @Test
    fun exceedingMaxDepthDropsOldest() {
        val s = ReaderBackStack(maxDepth = 3)
        s.recordJump("a")
        s.recordJump("b")
        s.recordJump("c")
        s.recordJump("d")
        assertEquals(3, s.size)
        // "a" rớt khỏi đáy → còn d, c, b
        assertEquals("d", s.pop())
        assertEquals("c", s.pop())
        assertEquals("b", s.pop())
        assertNull(s.pop())
    }

    @Test
    fun clearEmptiesStack() {
        val s = ReaderBackStack()
        s.recordJump("a")
        s.clear()
        assertFalse(s.canGoBack)
    }
}
