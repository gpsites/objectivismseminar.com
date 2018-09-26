const feedUrl = 'https://www.freeconferencecall.com/rss/podcast?id=2dd4f6a755aa45d0e05e72cc2367b2611992a141827eb6addeed79c5baf445fe_292812442';
const sessionsFilename = 'sessions.json';
const downloadsDirName = 'downloads';
const bucketPrefix = 'https://oapodcasts.s3.amazonaws.com/';

const fs = require('fs');
const https = require('https');
const promisify = require('util').promisify;
const parseXmlString = require('xml2js').parseString;
const readFile = promisify(fs.readFile);
const writeFile = promisify(fs.writeFile);
const Feed = require('feed').Feed;

const safeFilename = str => str.replace(':', '_');

const extractItems = json => {
  const items = json.rss.channel[0].item;
  var newitems = [];
  for (const item of items) {
    const newitem = {
      title: item.title.join(' '),
      // link: item.link.join(' '),
      sourcelink: item.enclosure[0].$.url,
      link: bucketPrefix + safeFilename(item.title.join(' ') + '.mp3'),
      pubDate: new Date(item.pubDate.join(' ')),
      // description: item.description.join(' ')
      description: 'Please visit www.ObjectivismSeminar.com for more information.',
    }
    newitems.push(newitem)
  }

  return newitems;
};

function fetchXmlFeedItems(url, callback) {
  const req = https.request(url, function (res) {
    var xml = '';

    res.on('data', function (chunk) {
      xml += chunk;
    });
    res.on('end', function () {
      parseXmlString(xml, function (err, result) {
        callback(null, extractItems(result));
      });
    });

    res.on('error', function (e) {
      callback(e, null);
    });
    res.on('timeout', function (e) {
      callback(e, null);
    });
  });
  req.end();
}
const fetchFeedItems = promisify(fetchXmlFeedItems)

var callbackDownload = function(url, dest, progress, cb) {
  var file = fs.createWriteStream(dest);
  var request = https.get(url, function(response) {
    response.pipe(file);
    file.on('finish', function() {
      file.close(cb);  // close() is async, call cb after close completes.
    });
    if (progress) { 
      let count = 0;
      response.on('data', chunk => progress(count += chunk.length));
    }
  }).on('error', function(err) { // Handle errors
    fs.unlinkSync(dest); // Delete the file async. (But we don't check the result)
    if (cb) cb(err.message);
  });
};
const download = promisify(callbackDownload);


const buildFeed = sessions => {
  const feed = new Feed({
    title: "The Objectivism Seminar",
    description: "A weekly online conference call to systematically study the philosophy of Objectivism via the works of prominent Rand scholars.",
    id: "https://www.objectivismseminar.com/",
    link: "https://www.objectivismseminar.com/",
    image: "https://www.objectivismseminar.com/assets/images/atlas.jpg",
    favicon: "https://www.objectivismseminar.com/assets/images/atlas-favicon.jpg",
    copyright: "All rights reserved, Greg Perkins",
    feedLinks: {
      rss: "https://www.objectivismseminar.com/archives/rss",
      json: "https://www.objectivismseminar.com/archives/json",
      atom: "https://www.objectivismseminar.com/archives/atom"
    },
    author: {
      name: "The Objectivism Seminar",
      email: "admin@objectivismseminar.com",
      link: "https://objectivismseminar.com"
    }
  });

  sessions.forEach(session => {
    feed.addItem({
      title: session.title,
      id: session.url,
      link: session.url,
      description: session.description,
      content: session.content,
      author: [
        {
          name: "Jane Doe",
          email: "janedoe@example.com",
          link: "https://example.com/janedoe"
        },
        {
          name: "Joe Smith",
          email: "joesmith@example.com",
          link: "https://example.com/joesmith"
        }
      ],
      contributor: [
        {
          name: "Shawn Kemp",
          email: "shawnkemp@example.com",
          link: "https://example.com/shawnkemp"
        },
        {
          name: "Reggie Miller",
          email: "reggiemiller@example.com",
          link: "https://example.com/reggiemiller"
        }
      ],
      date: session.date,
      image: session.image
    });
  });

  return feed;
}


try {
  main()
} catch (e) {
  console.log('MAIN ERROR:', e);
}


async function main() {
  const [feedItems, sessionData] = await Promise.all([fetchFeedItems(feedUrl), readFile(sessionsFilename)]);
  const sessions = JSON.parse(sessionData);

  var newItems = []
  for (const item of feedItems) {
    if (!sessions.find(x => x.title === item.title)) {
      newItems.push(item);
    }
  }

  if (!newItems.length) {
    console.log('no new sessions');
    return;
  }

  if (!fs.existsSync(downloadsDirName)) {
    fs.mkdirSync(downloadsDirName);
  }

  for (const item of newItems) {
    await download(item.sourcelink, downloadsDirName + '/' + safeFilename(item.title + '.mp3'), count => {
      process.stdout.cursorTo(0);
      process.stdout.write(`${item.title} ==> ${count} `);
    });
    console.log('complete');
    delete item.sourcelink;
  }

  const updatedSessions = [...newItems, ...sessions];
  await writeFile(sessionsFilename, JSON.stringify(updatedSessions, null, 2));

  const feed = buildFeed(updatedSessions);
  // console.log(feed.rss2());
  // Output: RSS 2.0
  // console.log(feed.atom1());
  // Output: Atom 1.0
  // console.log(feed.json1());
  // Output: JSON Feed 1.0
}

