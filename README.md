# Govstalk

They change their websites and hide things without notice. Let's ensure that doesn't happen again.

## How does it even?

It does even pretty simply. Look at <code>config.json.dist</code>. Make a copy of it. Modify it to suit.

the <code>fn</code> parameter in <code>targets</code> is used as the prefix for the filename used to store the data. It's pretty hacky. This is so we don't need to use a database.
