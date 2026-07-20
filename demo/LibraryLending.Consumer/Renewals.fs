module LibraryLending.Consumer.Renewals

open System
open LibraryLending.Loan

/// Renew a batch of loans, keeping only the ones that could be renewed.
let renewAll (today: DateOnly) (loans: Loan list) =
    loans |> List.choose (renew today)
