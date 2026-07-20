module LibraryLending.Book

type Book =
    { Title: string
      Author: string
      CopiesOnShelf: int }

/// A book can be lent when at least one copy is on the shelf.
let isAvailable (book: Book) = book.CopiesOnShelf > 0
