package com.example.notes

import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.notes.databinding.ActivityMainBinding
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * The note list. Every lifecycle hook we override calls super first; the
 * framework throws if onCreate does not.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val viewModel: NotesViewModel by viewModels()
    private val adapter = NotesAdapter(onClick = { note -> openEditor(note.id) })

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.notes.layoutManager = LinearLayoutManager(this)
        binding.notes.adapter = adapter
        binding.addNote.setOnClickListener { openEditor(noteId = null) }

        lifecycleScope.launch {
            viewModel.notes.collectLatest { notes -> adapter.submitList(notes) }
        }
    }

    override fun onResume() {
        super.onResume()
        viewModel.refresh()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = when (item.itemId) {
        R.id.action_sort -> {
            viewModel.toggleSort()
            true
        }
        R.id.action_settings -> {
            startActivity(SettingsActivity.intent(this))
            true
        }
        else -> super.onOptionsItemSelected(item)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putInt(KEY_SCROLL, binding.notes.computeVerticalScrollOffset())
    }

    private fun openEditor(noteId: Long?) {
        startActivity(EditorActivity.intent(this, noteId))
    }

    private companion object {
        const val KEY_SCROLL = "scroll"
    }
}
