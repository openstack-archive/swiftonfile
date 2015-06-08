###Last write wins: Swift vs SwiftOnFile

**OpenStack Swift:** The timestamp assigned to the request by proxy server
ultimately decides which "last" write wins. A "201 Created" is sent as
response to both the clients. Example:

Transaction T1 at time = t seconds:  
`curl -i http://vm1:8080/v1/AUTH_abc/c1/o1 -X PUT -T /tmp/reallybigfile`  
(Assume it takes 5 seconds to upload the *reallybigfile*)

Transaction T2 at time = (t + 0.01) seconds:  
`curl -i http://vm1:8080/v1/AUTH_abc/c1/o1 -X PUT -d 'tinydata'`  
(Assume it takes 1 second to upload this tiny data)

Here T2 wins although T1 will complete last. This is because T2 was the last
one to reach proxy server (the client facing server process that tags the
request with a timestamp).

Simultaneous PUT and DELETE illustrated: If a client has a long running PUT to
`AUTH_abc/c1/o1` and another client issues a DELETE on `AUTH_abc/c1/o1`
during the ongoing upload, the tombstone(.ts) will have a later timestamp and
will eventually take precedence even if the other upload finishes after. In
effect, to any new clients performing a HEAD/GET on `AUTH_abc/c1/o1`, the
client would recieve a `HTTP 404` response as the object stands deleted.

**SwiftOnFile:** Unlike in vanilla OpenStack Swift, SwiftOnFile does not
honour the timestamp set on request by the proxy server to decide which of
the write is the "last" one. In SwiftOnFile, the last write to complete
(at the filesystem layer) is the one that wins. Example:

Transaction T1 at time = t seconds:  
`curl -i http://vm1:8080/v1/AUTH_abc/c1/o1 -X PUT -T /tmp/reallybigfile`  
(Assume it takes 5 seconds to upload the *reallybigfile*)

Transaction T2 at time = (t + 0.01) seconds:  
`curl -i http://vm1:8080/v1/AUTH_abc/c1/o1 -X PUT -d 'tinydata'`  
(Assume it takes 1 second to upload this tiny data)

Here T1 wins although T2 is the last transaction among the two to reach the
proxy server. This is because T2 was the last to complete and will overwrite
the object created by T1. For a small duration, between T1 being completed and
T2 in progress, clients will be served the object created by T1.

Simultaneous PUT and DELETE illustrated: If a client has a long running PUT to
`AUTH_abc/c1/o1` and another client issues a DELETE on `AUTH_abc/c1/o1` during
the ongoing upload, the DELETE request would be responded with either of these:

* `HTTP 404` as the file does not exist because it's still being uploaded to
   a temp path.
* `HTTP 204` as an older version of the file did exist and the DELETE was
   successful.

In effect, after completion of both PUT and DELETE, to any new client
performing a HEAD/GET on `AUTH_abc/c1/o1`, the client would recieve the newer
object uploaded by last PUT operation.
