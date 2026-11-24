# Team profiles

Every person at Gradiated has one folder here, named after them:

```
content/team/ada-lovelace/
  ada-lovelace.md        the profile
  images/
    profile/             profile picture which shmo will handle
    gallery/             your gallery section
```

The folder becomes the page at `/team/ada-lovelace/`, the card on `/about/`,
the entry in the team navigation, and the pin on the map on `/team/`.

## Editing your profile

1. Find your folder. If you are new and do not have one, copy `_template`
   and rename the copy and the `.md` file in it to your name, in lowercase
   with hyphens. The folder's name is your page's address.
2. Fill in the top block of your `.md` file and write under the headings.
3. Add pictures for your Gallery to `images/gallery/`. On GitHub's website,
   "Add file → Upload files" inside that folder does it.
4. Open a pull request. The build checks your folder and names any mistake.

## The top block

Only `name` and `role` are required.

- `summary`: one or two sentences. It shows on your card on `/about/`, and as
  your bio until you write one.
- `location`: public, and puts you on the map. Give the `city` you are happy
  to list and the `country` as it should read ("UK"); the flag and the map
  pin are worked out from those. Leave it out to stay off the map. If either
  comes out wrong, add `latitude` and `longitude`, or a two-letter
  `countryCode`.
- `links`: `website`, `github`, `linkedin` and `x`, each a full `https://`
  link, shown as icons beside your name.
- `captions`: a caption for a gallery picture, by its file name.

## Sections

Each `##` heading in your file is a section of your page and an entry in its
contents. A section with nothing under it is hidden, so leave the headings in
place until you have something to say.

- **Posts.** Anything you publish in the Gradiated Library, with you named as
  author, is listed for you. Add writing from anywhere else as a list of
  links, each with an optional note:

  ```md
  - [Title of the post](https://example.com/your-post) — where or when
  ```

- **Gallery.** Shows the pictures in `images/gallery/`, in file-name order;
  number the files (`01-desk.jpg`, `02-boat.jpg`) to set it. Add them as they
  are, straight off a phone or camera, as JPG or PNG. The site resizes them,
  which also strips the location and camera details a photograph carries.
  iPhone HEIC files need saving as JPG first.
