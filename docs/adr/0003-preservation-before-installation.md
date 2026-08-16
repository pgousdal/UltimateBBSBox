# ADR 0003: Preserve before install

Status: Accepted

Every network-acquired installation artifact is hashed, assigned provenance, and preserved immutably before installers may consume it. Derived artifacts never replace originals. Redistribution is deny-by-default and separately recorded from local preservation/install rights.
