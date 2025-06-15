// rcon.js
const Q3RCon = require("quake3-rcon");

const [,, address, port, password, ...commandParts] = process.argv;
const command = commandParts.join(" ");

const rcon = new Q3RCon({
    address,
    port: parseInt(port, 10),
    password,
    debug: false
});

rcon.send(command, (response) => {
    console.log(response || "(no response)");
    process.exit(0);
});
