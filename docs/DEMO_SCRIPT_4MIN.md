# Demo script — 4 minutes

Read straight through while you drive the screen. About 4:15 at a natural pace.

---

Every case generates paper. The FIR, witness statements, the charge sheet, forensic reports. Most of
it lives in folders or spread across a few computers. Slow to find, easy to change without anyone
noticing, hard to audit. So we built a secure document system for it — built around the case, not
around a suspect.

You sign in as an officer. The file is classified before it opens, and everything you do is tied to
your name. The dashboard is a register of cases: how many are on file, how many documents back them
up, how they split by offence and by stage. Search is forgiving — part of an FIR number, the title, or
just the city.

Open a case and everything about it is in one place. Now here's the part that really matters. Every
person carries the role the document actually gave them. This one's a suspect. This one's a witness.
This one is just mentioned in passing. A witness is not a suspect, and the system refuses to blur them
into one list of names. The documents it's built on sit right below, and you can open the original
without leaving the page — exactly as uploaded, and you can't edit it.

So how does it actually read a document? Worth walking through, because not all of it is AI, and
that's deliberate.

A scan goes through OCR first to pull text off the image. Then anything with a fixed shape — FIR
numbers, phone numbers, vehicle numbers — we simply pattern-match. You don't need a model for
something that never varies. For names of people, places and companies we use a model we trained
ourselves: a trained model, but not a chatbot. Relationships that come straight from the FIR's layout
come from rules. Only the messy part, the story written in sentences, goes to a language model — and
that model runs on this machine, so nothing is sent anywhere. We make it answer in a fixed format and
point at the exact line it read, then our own code checks everything it said.

And then it stops. Nothing enters the case record until an officer says yes. Every name and connection
is shown with the sentence it came from, and you keep it or reject it. If a name already exists, we
show you that person and let you decide instead of guessing. Only when you confirm is anything saved.

We also index the document so it can be searched. The text is cut into small overlapping chunks, and
each chunk is stored two ways: once for keyword search, once as a set of numbers that captures its
meaning. Ask a question and both searches run, we blend the results, drop near-duplicates, and look
only inside that officer's documents for that case. That's the retrieval layer, and it's why the
system can quote a line from an FIR that never became a formal link.

The case summary uses all of it. It reads the confirmed record plus those chunks and writes a short
timeline: what happened, who's involved and in what role, the dates, the evidence, where things stand.
Every line tells you which document it came from — click it and that document opens. If the AI writes
something it can't point to, we throw the line away rather than show it. Allegations stay allegations.
Nothing here says anyone is guilty.

There's a network view going four steps out, where clicking a connection shows the sentence behind
it, and a workspace for asking questions across several cases at once. The patterns there — who keeps
showing up, which address repeats — are worked out by ordinary code, not the AI. The AI only puts them
into words. It works in Hindi too, and the model is local, so none of these documents leave the
building.

Where we'd go next is blockchain. Confirmation is already the moment a document becomes part of the
record. Write a fingerprint of that document and that decision onto a private blockchain, and the
record isn't just protected, it's provable. An officer could show a court this charge sheet is exactly
the one signed off that day, and if one character changed later, everyone would know. We have the
audit trail today. The blockchain is what makes it stand up in court.
