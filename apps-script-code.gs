// Music City Retreat - Guest WiFi Captive Portal Backend
// Logs submissions to a Google Sheet and sends a verification email with a unique link.
// Deploy as a Web App with:
//   Execute as: Me (your Google account)
//   Who has access: Anyone

// --- CONFIG -------------------------------------------------------
var SHEET_ID = 'REPLACE_WITH_YOUR_SHEET_ID';   // from the Sheet URL
var SHEET_NAME = 'Guests';                      // tab name inside the Sheet
var FROM_NAME = 'Music City Retreat';
var PROPERTY_NAME = 'Music City Retreat';
var WIFI_SSID = 'REPLACE_WITH_GUEST_WIFI_SSID';
var WIFI_PASSWORD = 'REPLACE_WITH_GUEST_WIFI_PASSWORD';
var REDIRECT_URL = 'http://192.168.0.217/welcome_sign.html';
var REDIRECT_SECONDS = 3;
// ------------------------------------------------------------------

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var name = String(data.name || '').trim();
    var email = String(data.email || '').trim();
    var stay = String(data.stay || '').trim();

    if (!name || !email || !stay) {
      return ContentService.createTextOutput(JSON.stringify({ ok: false, error: 'missing fields' }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    var token = Utilities.getUuid();
    var timestamp = new Date();

    var sheet = getSheet_();
    sheet.appendRow([timestamp, name, email, stay, token, 'FALSE', '']);

    var scriptUrl = ScriptApp.getService().getUrl();
    var verifyLink = scriptUrl + '?token=' + encodeURIComponent(token);
    sendVerificationEmail_(email, name, verifyLink);

    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  var token = (e && e.parameter && e.parameter.token) ? String(e.parameter.token) : '';

  if (!token) {
    return htmlPage_('Invalid link', 'No verification token was provided.');
  }

  var sheet = getSheet_();
  var rows = sheet.getDataRange().getValues();

  for (var i = 1; i < rows.length; i++) {
    if (rows[i][4] === token) {
      if (rows[i][5] === 'TRUE') {
        return htmlPage_('Already verified', 'This email has already been verified. Redirecting you to the welcome page...', REDIRECT_URL);
      }
      sheet.getRange(i + 1, 6).setValue('TRUE');
      sheet.getRange(i + 1, 7).setValue(new Date());
      return htmlPage_('Verified!', 'Thank you, ' + rows[i][1] + '. Your email is verified. Redirecting you to the welcome page...', REDIRECT_URL);
    }
  }

  return htmlPage_('Not found', 'That verification link is invalid or expired.');
}

function getSheet_() {
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(['Timestamp', 'Name', 'Email', 'Stay', 'Token', 'Verified', 'VerifiedAt']);
  }
  return sheet;
}

function sendVerificationEmail_(email, name, verifyLink) {
  var subject = 'Verify your ' + PROPERTY_NAME + ' WiFi access';
  var plain = 'Hi ' + name + ',\n\n' +
    'Thanks for connecting to ' + PROPERTY_NAME + ' guest WiFi.\n\n' +
    'Click the link below to verify your email:\n' + verifyLink + '\n\n' +
    'WiFi network: ' + WIFI_SSID + '\n' +
    'Password: ' + WIFI_PASSWORD + '\n\n' +
    'Enjoy your stay!\n' + FROM_NAME;

  var html =
    '<div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; color: #2d1b3d;">' +
      '<h2 style="margin: 0 0 12px 0;">Welcome to ' + PROPERTY_NAME + '</h2>' +
      '<p>Hi ' + name + ',</p>' +
      '<p>Thanks for connecting to our guest WiFi. Please verify your email by clicking the button below:</p>' +
      '<p style="text-align: center; margin: 28px 0;">' +
        '<a href="' + verifyLink + '" style="display: inline-block; background: linear-gradient(135deg, #FF5E62 0%, #FF9966 100%); color: #ffffff; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-weight: 600;">Verify email</a>' +
      '</p>' +
      '<p style="color: #6b5b73; font-size: 14px;">If the button does not work, copy and paste this link:<br>' +
      '<span style="word-break: break-all;">' + verifyLink + '</span></p>' +
      '<hr style="border: none; border-top: 1px solid #e5e0e8; margin: 24px 0;">' +
      '<p style="margin: 0;"><strong>WiFi network:</strong> ' + WIFI_SSID + '<br>' +
      '<strong>Password:</strong> ' + WIFI_PASSWORD + '</p>' +
      '<p style="color: #6b5b73; font-size: 13px; margin-top: 24px;">Enjoy your stay!<br>' + FROM_NAME + '</p>' +
    '</div>';

  MailApp.sendEmail({
    to: email,
    subject: subject,
    body: plain,
    htmlBody: html,
    name: FROM_NAME
  });
}

function htmlPage_(title, message, redirectUrl) {
  var redirectMeta = redirectUrl ? '<meta http-equiv="refresh" content="' + REDIRECT_SECONDS + ';url=' + redirectUrl + '">' : '';
  var redirectScript = redirectUrl ? '<script>setTimeout(function(){window.top.location.href="' + redirectUrl + '"},' + (REDIRECT_SECONDS * 1000) + ');</script>' : '';
  var html =
    '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' + redirectMeta + '<title>' + title + '</title>' +
    '<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:linear-gradient(160deg,#2B1055 0%,#7597DE 30%,#FF5E62 65%,#FFB86C 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;margin:0}' +
    '.card{background:#fff;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,.3);padding:40px 32px;max-width:440px;width:100%;text-align:center;color:#2d1b3d}' +
    'h1{margin:0 0 12px 0;font-size:24px}p{color:#6b5b73;line-height:1.5}</style></head>' +
    '<body><div class="card"><h1>' + title + '</h1><p>' + message + '</p></div>' + redirectScript + '</body></html>';
  return HtmlService.createHtmlOutput(html).setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
