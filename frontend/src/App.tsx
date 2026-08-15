import { useState, type FormEvent } from 'react'
import './App.css'

// SPIKE: hand-written contract type. This violates CLAUDE.md rule 2 — the real
// type is generated from /openapi.json in US-04. Note `price` is a string, not
// a number: Pydantic serialises Decimal as a JSON string to avoid float error.
interface BookInfo {
  isbn: string
  title: string
  authors: string[]
  cover_url: string | null
  price: string | null
  currency: string | null
  description: string
  description_is_generated: boolean
  sources: string[]
}

const API_BASE = 'http://localhost:8000'

function App() {
  const [isbn, setIsbn] = useState('')
  const [book, setBook] = useState<BookInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function search(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError(null)
    setBook(null)

    try {
      const response = await fetch(`${API_BASE}/api/books/${isbn.trim()}`)
      if (!response.ok) {
        setError(
          response.status === 404
            ? `No book found for ISBN ${isbn.trim()}`
            : `Lookup failed (${response.status})`,
        )
        return
      }
      setBook((await response.json()) as BookInfo)
    } catch {
      setError('Could not reach the lookup service')
    } finally {
      setLoading(false)
    }
  }

  const price =
    book?.price != null ? `${book.price} ${book.currency ?? ''}`.trim() : 'Not available'

  return (
    <main>
      <h1>Please enter the ISBN number</h1>

      <form onSubmit={search}>
        <input
          type="text"
          value={isbn}
          onChange={(event) => setIsbn(event.target.value)}
          placeholder="9780132350884"
          aria-label="ISBN"
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {book && (
        <table>
          <tbody>
            <tr>
              <th scope="row">Cover</th>
              <td>
                {book.cover_url ? (
                  <img src={book.cover_url} alt={`Cover of ${book.title}`} width="120" />
                ) : (
                  'No cover'
                )}
              </td>
            </tr>
            <tr>
              <th scope="row">Title</th>
              <td>{book.title}</td>
            </tr>
            <tr>
              <th scope="row">Authors</th>
              <td>{book.authors.join(', ')}</td>
            </tr>
            <tr>
              <th scope="row">Price</th>
              <td>{price}</td>
            </tr>
            <tr>
              <th scope="row">Description</th>
              <td>{book.description || '—'}</td>
            </tr>
            <tr>
              <th scope="row">Sources</th>
              <td>{book.sources.join(', ')}</td>
            </tr>
          </tbody>
        </table>
      )}
    </main>
  )
}

export default App
