module LibraryLending.Consumer.Memberships

open System
open LibraryLending.Member

/// Renew every membership for another year.
let renewAll (today: DateOnly) (members: Member list) =
    members |> List.map (renew today)
