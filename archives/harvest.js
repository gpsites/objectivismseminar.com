const feedUrl = 'https://www.freeconferencecall.com/rss/podcast?id=2dd4f6a755aa45d0e05e72cc2367b2611992a141827eb6addeed79c5baf445fe_292812442';
const sessionsFilename = 'sessions.json';
const feedFilename = 'rss.xml';
const downloadsDirName = 'downloads';
const bucketPrefix = 'https://oapodcasts.s3.amazonaws.com/';

const fs = require('fs');
const https = require('https');
const promisify = require('util').promisify;
const parseXmlString = require('xml2js').parseString;
const readFile = promisify(fs.readFile);
const writeFile = promisify(fs.writeFile);
const Podcast = require('podcast');

const safeFilename = str => str.replace(/[:/]/g, '_');

const extractItems = json => {
  const items = json.rss.channel[0].item;
  var newitems = [];
  for (const item of items) {
    const newitem = {
      title: item.title.join(' '),
      // link: item.link.join(' '),
      sourcelink: item.enclosure[0].$.url,
      link: encodeURI(bucketPrefix + safeFilename(item.title.join(' ') + '.mp3')),
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
  const feed = new Podcast({
    title: "The Objectivism Seminar",
    description: "A weekly online conference call to systematically study the philosophy of Objectivism via the works of prominent Rand scholars.",
    feedUrl: "https://www.objectivismseminar.com/archives/rss",
    siteUrl: "https://www.objectivismseminar.com/",
    imageUrl: "https://www.objectivismseminar.com/assets/images/atlas-square.jpg",
    author: "Greg Perkins, Host",
    itunesOwner: { name: "Greg Perkins", email: "greg@ecosmos.com" },
    itunesExplicit: true,
    itunesCategory: [{text: "Society & Culture", subcats: [{text: "Philosophy", subcats: []}]}],
    language: "en",
    pubDate: new Date(),
  });

  sessions.forEach(session => {
    feed.addItem({
      title: session.title,
      description: session.description,
      
      url: session.link,
      link: session.link,
      category: 'Philosophy',
      guid: session.link,
      date: session.pubDate,
      enclosure: {
        url: session.link,
      }
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
  const skipDownloads= process.argv.length > 2 && process.argv[2] == "skip";
  const [feedItems, sessionData] = await Promise.all([fetchFeedItems(feedUrl), readFile(sessionsFilename)]);
  const sessions = JSON.parse(sessionData);
  for (const session of sessions) {
    session.pubDate = new Date(session.pubDate);
  }

  var newItems = []
  for (const item of feedItems) {
    if (!sessions.find(x => x.link === item.link)) {
      newItems.push(item);
    }
  }

  if (!newItems.length) {
    console.log('no new sessions');
  }

  if (!fs.existsSync(downloadsDirName)) {
    fs.mkdirSync(downloadsDirName);
  }

  if (!skipDownloads) {
  for (const item of newItems) {
    await download(item.sourcelink, downloadsDirName + '/' + safeFilename(item.title + '.mp3'), count => {
      process.stdout.cursorTo(0);
      process.stdout.write(`${item.title} ==> ${count} `);
    });
    console.log('complete');
    delete item.sourcelink;
  }
  }

  const updatedSessions = [...newItems, ...sessions];

  const feed = buildFeed(updatedSessions);

  await Promise.all([writeFile(sessionsFilename, JSON.stringify(updatedSessions, null, 2)), writeFile(feedFilename, feed.buildXml())]);
  console.log('wrote sessions.json and rss feed files')
}

