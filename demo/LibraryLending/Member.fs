module LibraryLending.Member

open System

type Member =
    { Name: string
      LoansAllowed: int
      MembershipExpires: DateOnly }

/// Renew a membership: push its expiry date out by a year.
let renew (today: DateOnly) (m: Member) =
    { m with MembershipExpires = today.AddYears 1 }
