module LibraryLending.Loan

open System
open LibraryLending.Book
open LibraryLending.Member

/// A loan may be renewed at most this many times.
let renewalLimit = 2

type Loan =
    { Book: Book
      Borrower: Member
      DueDate: DateOnly
      RenewalsUsed: int }

/// A loan is overdue once its due date has passed.
let isOverdue (today: DateOnly) (loan: Loan) = today > loan.DueDate

/// Extend the due date by two weeks — unless the renewal limit is
/// reached, or the loan is already overdue.
let renew (today: DateOnly) (loan: Loan) =
    if loan.RenewalsUsed >= renewalLimit then None
    elif isOverdue today loan then None
    else Some { loan with
                  DueDate = loan.DueDate.AddDays 14
                  RenewalsUsed = loan.RenewalsUsed + 1 }
