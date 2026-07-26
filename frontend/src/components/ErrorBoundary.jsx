import { Component } from 'react'
import { AlertTriangle } from 'lucide-react'

/**
 * Catches render-time crashes so one bad page doesn't blank the whole app.
 *
 * Most of what this app renders is LLM-authored and stored loosely (notably
 * `example_sentences`, a JSON string in a text column), so a malformed record
 * reaching a render path is a realistic failure — not just a programming bug.
 * Keeping the boundary inside the layout means the nav stays usable and the
 * user can route away from the broken page.
 */
export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Render error:', error, info)
  }

  componentDidUpdate(prevProps) {
    // Reset on navigation so a crash on one route doesn't stick to the next.
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null })
    }
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <div className="max-w-lg mx-auto text-center py-12 space-y-4">
        <AlertTriangle className="mx-auto text-orange-400" size={40} />
        <h2 className="text-xl font-semibold">Something broke on this page</h2>
        <p className="text-sm text-gray-500">
          {this.state.error?.message || 'An unexpected error occurred.'}
        </p>
        <div className="flex gap-3 justify-center pt-1">
          <button
            onClick={() => this.setState({ error: null })}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-500"
          >
            Try again
          </button>
          <button
            onClick={() => window.location.reload()}
            className="border border-gray-700 text-gray-300 px-4 py-2 rounded-lg text-sm hover:bg-gray-800"
          >
            Reload
          </button>
        </div>
      </div>
    )
  }
}
